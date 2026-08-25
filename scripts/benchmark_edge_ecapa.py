"""Measure ONNX ECAPA size, ARM CPU latency, memory, and INT8 fidelity."""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing
import platform
import resource
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from voiceid.adapters.audio.energy_vad import EnergyVoiceActivityDetector
from voiceid.adapters.audio.wave_decoder import PcmWaveDecoder
from voiceid.adapters.evaluation.json_audio_manifest import load_audio_trial_manifest
from voiceid.adapters.models.edge_onnx import load_edge_artifact_manifest
from voiceid.application.preprocessing import AudioPreprocessor
from voiceid.domain.edge_profile import load_edge_profile
from voiceid.domain.evaluation import TrialPartition
from voiceid.domain.metrics import estimate_eer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_manifest", type=Path)
    parser.add_argument("--profile", type=Path, default=Path("config/edge-profile-v1.json"))
    parser.add_argument(
        "--audio-manifest",
        type=Path,
        default=Path("data/raw/librispeech/voiceid-clean-v1/audio-trials.json"),
    )
    parser.add_argument(
        "--audio-root",
        type=Path,
        default=Path("data/raw/librispeech/voiceid-clean-v1"),
    )
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--runs", type=int, default=40)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    if min(arguments.samples, arguments.warmups, arguments.runs) <= 0:
        parser.error("samples, warmups, and runs must be positive")

    artifact = load_edge_artifact_manifest(arguments.artifact_manifest)
    profile = load_edge_profile(arguments.profile)
    if artifact.source_model_id != profile.source_model_id:
        parser.error("edge artifact and profile refer to different source models")

    waveforms, speakers = _evaluation_waveforms(
        arguments.audio_manifest,
        arguments.audio_root,
        arguments.samples,
        round(profile.window_seconds * profile.sample_rate),
    )
    context = multiprocessing.get_context("spawn")
    results: dict[str, dict[str, Any]] = {}
    for name, model in (("fp32", artifact.fp32.path), ("int8", artifact.int8.path)):
        parent, child = context.Pipe(duplex=False)
        process = context.Process(
            target=_worker,
            args=(child, model, waveforms, arguments.warmups, arguments.runs),
        )
        process.start()
        child.close()
        results[name] = parent.recv()
        process.join()
        if process.exitcode != 0 or "error" in results[name]:
            parser.error(f"{name} benchmark failed: {results[name].get('error', process.exitcode)}")

    fidelity = _fidelity(results["fp32"]["embeddings"], results["int8"]["embeddings"], speakers)
    int8_size_mib = artifact.int8.size_bytes / 1_048_576
    checks = {
        "artifact_size": int8_size_mib <= profile.budgets.artifact_size_mib,
        "model_graph_p95_latency": (
            results["int8"]["latency_ms"]["p95"] <= profile.budgets.model_core_p95_ms
        ),
        "peak_process_rss": (
            results["int8"]["peak_process_rss_mib"] <= profile.budgets.peak_working_set_mib
        ),
        "minimum_embedding_cosine": (
            fidelity["embedding_cosine"]["minimum"] >= profile.fidelity.minimum_embedding_cosine
        ),
        "p95_absolute_score_delta": (
            fidelity["verification_score_delta"]["p95"] <= profile.fidelity.p95_absolute_score_delta
        ),
        "eer_increase": (
            fidelity["observed_eer"]["increase_percentage_points"]
            <= profile.fidelity.maximum_eer_increase_points
        ),
    }
    for result in results.values():
        result.pop("embeddings")
    payload = {
        "schema_version": "voiceid-edge-benchmark/v1",
        "profile_id": profile.profile_id,
        "artifact_id": artifact.artifact_id,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "scope": {
            "measured": "full ONNX graph on this host CPU",
            "not_measured": [
                "phone hardware",
                "wearable microphone accuracy",
                "device energy consumption",
                "Bluetooth capture latency",
            ],
            "audio_partition": "evaluation",
            "audio_samples": len(waveforms),
            "window_samples": len(waveforms[0]),
        },
        "artifacts": {
            "fp32_size_mib": artifact.fp32.size_bytes / 1_048_576,
            "fp32_sha256": artifact.fp32.sha256,
            "int8_size_mib": int8_size_mib,
            "int8_sha256": artifact.int8.sha256,
            "size_reduction_percent": 100.0
            * (1.0 - artifact.int8.size_bytes / artifact.fp32.size_bytes),
        },
        "runtime": results,
        "fidelity": fidelity,
        "budget_checks": checks,
        "all_locally_measurable_budgets_pass": all(checks.values()),
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8"
    )
    print(f"report={arguments.output}")
    print(f"int8_p95_ms={results['int8']['latency_ms']['p95']:.3f}")
    print(f"int8_peak_rss_mib={results['int8']['peak_process_rss_mib']:.3f}")
    print(f"minimum_embedding_cosine={fidelity['embedding_cosine']['minimum']:.6f}")
    print(f"all_locally_measurable_budgets_pass={all(checks.values())}")


def _worker(
    connection: Any,
    model_path: Path,
    waveforms: list[list[float]],
    warmups: int,
    runs: int,
) -> None:
    try:
        import numpy
        import onnxruntime

        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        started = time.perf_counter()
        session = onnxruntime.InferenceSession(
            str(model_path), options, providers=["CPUExecutionProvider"]
        )
        load_ms = (time.perf_counter() - started) * 1000.0
        arrays = [numpy.asarray(waveform, dtype=numpy.float32)[None, :] for waveform in waveforms]
        for index in range(warmups):
            session.run(["embedding"], {"waveform": arrays[index % len(arrays)]})
        latencies: list[float] = []
        for index in range(runs):
            started = time.perf_counter()
            session.run(["embedding"], {"waveform": arrays[index % len(arrays)]})
            latencies.append((time.perf_counter() - started) * 1000.0)
        embeddings = [
            session.run(["embedding"], {"waveform": waveform})[0].reshape(-1).tolist()
            for waveform in arrays
        ]
        connection.send(
            {
                "runtime": onnxruntime.__version__,
                "provider": session.get_providers()[0],
                "threads": 1,
                "session_load_ms": load_ms,
                "latency_ms": {
                    "runs": len(latencies),
                    "mean": statistics.fmean(latencies),
                    "p50": statistics.median(latencies),
                    "p95": _percentile(latencies, 0.95),
                    "maximum": max(latencies),
                },
                "peak_process_rss_mib": _peak_rss_mib(),
                "embeddings": embeddings,
            }
        )
    except Exception as error:  # noqa: BLE001 - child must return framework failures to parent.
        connection.send({"error": f"{type(error).__name__}: {error}"})
    finally:
        connection.close()


def _evaluation_waveforms(
    manifest_path: Path, audio_root: Path, count: int, window_samples: int
) -> tuple[list[list[float]], list[str]]:
    manifest = load_audio_trial_manifest(manifest_path)
    unique: dict[str, tuple[str, str]] = {}
    for trial in manifest.trials:
        if trial.partition is TrialPartition.EVALUATION:
            unique.setdefault(trial.sample.sha256, (trial.sample.path, trial.probe_speaker_id))
    preprocessor = AudioPreprocessor(PcmWaveDecoder(), EnergyVoiceActivityDetector())
    waveforms: list[list[float]] = []
    speakers: list[str] = []
    for digest, (relative, speaker) in sorted(unique.items(), key=lambda item: item[1][0]):
        path = audio_root / relative
        import hashlib

        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"benchmark audio failed integrity verification: {path.name}")
        processed = preprocessor.process(path.read_bytes()).processed
        samples = [
            sample
            for segment in processed.speech_segments
            for sample in processed.audio.samples[segment.start_sample : segment.end_sample]
        ]
        if len(samples) < window_samples:
            continue
        waveforms.append(samples[:window_samples])
        speakers.append(speaker)
        if len(waveforms) == count:
            break
    if len(waveforms) != count:
        raise ValueError("evaluation partition does not contain enough fixed-window samples")
    if len(set(speakers)) < 2:
        raise ValueError("benchmark samples must contain multiple speakers")
    return waveforms, speakers


def _fidelity(
    fp32: list[list[float]], int8: list[list[float]], speakers: list[str]
) -> dict[str, Any]:
    cosines = [_cosine(left, right) for left, right in zip(fp32, int8, strict=True)]
    fp32_genuine: list[float] = []
    fp32_impostor: list[float] = []
    int8_genuine: list[float] = []
    int8_impostor: list[float] = []
    deltas: list[float] = []
    for left in range(len(fp32)):
        for right in range(left + 1, len(fp32)):
            baseline = _cosine(fp32[left], fp32[right])
            quantized = _cosine(int8[left], int8[right])
            deltas.append(abs(baseline - quantized))
            if speakers[left] == speakers[right]:
                fp32_genuine.append(baseline)
                int8_genuine.append(quantized)
            else:
                fp32_impostor.append(baseline)
                int8_impostor.append(quantized)
    if not fp32_genuine or not fp32_impostor:
        raise ValueError("fidelity cohort requires genuine and impostor sample pairs")
    fp32_eer = estimate_eer(fp32_genuine, fp32_impostor).balanced_error_rate
    int8_eer = estimate_eer(int8_genuine, int8_impostor).balanced_error_rate
    return {
        "embedding_cosine": {
            "minimum": min(cosines),
            "median": statistics.median(cosines),
            "mean": statistics.fmean(cosines),
        },
        "verification_score_delta": {
            "pairs": len(deltas),
            "mean": statistics.fmean(deltas),
            "p95": _percentile(deltas, 0.95),
            "maximum": max(deltas),
        },
        "observed_eer": {
            "fp32": fp32_eer,
            "int8": int8_eer,
            "increase_percentage_points": max(0.0, (int8_eer - fp32_eer) * 100.0),
            "cohort_limitation": "small pairwise subset; not the frozen VoiceID calibration protocol",
        },
    }


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _peak_rss_mib() -> float:
    value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value / (1024.0 * 1024.0) if platform.system() == "Darwin" else value / 1024.0


if __name__ == "__main__":
    main()
