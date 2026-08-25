"""Evaluate INT8 ECAPA with clean enrollment and reproducible channel proxies."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import random
import statistics
import wave
from datetime import UTC, datetime
from pathlib import Path

from voiceid.adapters.audio.energy_vad import EnergyVoiceActivityDetector
from voiceid.adapters.audio.wave_decoder import PcmWaveDecoder
from voiceid.adapters.evaluation.filesystem import HashedAudioFileReader
from voiceid.adapters.evaluation.json_audio_manifest import load_audio_trial_manifest
from voiceid.adapters.models.edge_onnx import OnnxEcapaRuntime, load_edge_artifact_manifest
from voiceid.adapters.models.speechbrain_ecapa import SpeechBrainEcapaEmbedder
from voiceid.adapters.repositories.memory import InMemoryVoiceTemplateRepository
from voiceid.application.enrollment import EnrollmentService
from voiceid.application.evaluation import evaluate_scored_trials
from voiceid.application.preprocessing import AudioPreprocessor
from voiceid.application.trial_scoring import AudioTrialScorer
from voiceid.application.verification import VerificationService
from voiceid.domain.audio import AudioBuffer
from voiceid.domain.evaluation import (
    AudioFileReference,
    ScoredTrialManifest,
    TrialLabel,
    TrialPartition,
)
from voiceid.domain.metrics import estimate_eer, rates_at_threshold

CONDITIONS = (
    "clean",
    "wearable_bandlimited_proxy",
    "additive_noise_15db_proxy",
    "bandlimited_noise_10db_proxy",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_manifest", type=Path)
    parser.add_argument(
        "audio_manifest",
        type=Path,
        default=Path("experiments/librispeech-clean-v2/audio-trials.json"),
    )
    parser.add_argument(
        "--audio-root",
        type=Path,
        default=Path("data/raw/librispeech/voiceid-clean-v2"),
    )
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    edge_manifest = load_edge_artifact_manifest(arguments.artifact_manifest)
    audio_manifest = load_audio_trial_manifest(arguments.audio_manifest)
    probe_hashes = {trial.sample.sha256 for trial in audio_manifest.trials}
    scored: dict[str, ScoredTrialManifest] = {}
    for condition in CONDITIONS:
        runtime = OnnxEcapaRuntime(arguments.artifact_manifest, variant="int8")
        embedder = SpeechBrainEcapaEmbedder(runtime=runtime)
        preprocessor = AudioPreprocessor(PcmWaveDecoder(), EnergyVoiceActivityDetector())
        repository = InMemoryVoiceTemplateRepository()
        reader = ChannelProxyAudioReader(
            HashedAudioFileReader(arguments.audio_root),
            condition=condition,
            transformed_hashes=probe_hashes,
        )
        scored[condition] = AudioTrialScorer(
            EnrollmentService(preprocessor, embedder, repository),
            VerificationService(preprocessor, embedder, repository),
            reader,
        ).score(audio_manifest)
        print(f"condition={condition} trials={len(scored[condition].trials)}")

    clean_report = evaluate_scored_trials(scored["clean"])
    clean_threshold = clean_report.selected_threshold
    clean_scores = {trial.trial_id: trial.score for trial in scored["clean"].trials}
    conditions = {
        name: _condition_summary(manifest, clean_threshold, clean_scores)
        for name, manifest in scored.items()
    }
    clean_eer = conditions["clean"]["evaluation"]["observed_eer"]
    for summary in conditions.values():
        summary["evaluation"]["eer_increase_percentage_points"] = max(
            0.0, 100.0 * (summary["evaluation"]["observed_eer"] - clean_eer)
        )

    payload = {
        "schema_version": "voiceid-edge-channel-evaluation/v1",
        "artifact_id": edge_manifest.artifact_id,
        "source_model_id": edge_manifest.source_model_id,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "dataset": {
            "id": audio_manifest.dataset_id,
            "version": audio_manifest.dataset_version,
            "manifest_sha256": hashlib.sha256(arguments.audio_manifest.read_bytes()).hexdigest(),
        },
        "protocol": {
            "enrollment_channel": "clean",
            "probe_channels": list(CONDITIONS),
            "threshold_source": "clean_int8_development_min_dcf",
            "selected_threshold": clean_threshold,
            "raw_audio_published": False,
            "per_trial_scores_published": False,
        },
        "conditions": conditions,
        "limitations": [
            "Band limiting and deterministic additive noise are software proxies, not recordings from AirPods, Ray-Ban Meta, or another wearable.",
            "LibriSpeech read speech is not representative of spontaneous wearable commands.",
            "The small correlated cohort cannot establish production biometric accuracy.",
            "No replay, Bluetooth transport, wind, motion, packet-loss, or device-energy measurement is included.",
        ],
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8"
    )
    print(f"report={arguments.output}")


class ChannelProxyAudioReader:
    """Verify original bytes first, then transform probes without changing enrollment audio."""

    def __init__(
        self,
        reader: HashedAudioFileReader,
        *,
        condition: str,
        transformed_hashes: set[str],
    ) -> None:
        if condition not in CONDITIONS:
            raise ValueError("unknown channel proxy")
        self._reader = reader
        self._condition = condition
        self._transformed_hashes = transformed_hashes

    def read(self, reference: AudioFileReference) -> bytes:
        payload = self._reader.read(reference)
        if self._condition == "clean" or reference.sha256 not in self._transformed_hashes:
            return payload
        audio = PcmWaveDecoder().decode(payload)
        samples = list(audio.samples)
        if "bandlimited" in self._condition:
            samples = _bandlimit(samples, audio.sample_rate)
        if "noise_15db" in self._condition:
            samples = _add_noise(samples, 15.0, reference.sha256)
        if "noise_10db" in self._condition:
            samples = _add_noise(samples, 10.0, reference.sha256)
        return _pcm_wave(
            AudioBuffer(tuple(max(-1.0, min(1.0, value)) for value in samples), audio.sample_rate)
        )


def _condition_summary(
    manifest: ScoredTrialManifest, threshold: float, clean_scores: dict[str, float]
) -> dict[str, object]:
    evaluation = manifest.trials_for(TrialPartition.EVALUATION)
    genuine = [trial.score for trial in evaluation if trial.label is TrialLabel.GENUINE]
    impostor = [trial.score for trial in evaluation if trial.label is TrialLabel.IMPOSTOR]
    eer = estimate_eer(genuine, impostor)
    locked = rates_at_threshold(genuine, impostor, threshold)
    deltas = [abs(trial.score - clean_scores[trial.trial_id]) for trial in manifest.trials]
    return {
        "trials": len(manifest.trials),
        "absolute_score_delta_from_clean": {
            "mean": statistics.fmean(deltas),
            "p95": _percentile(deltas, 0.95),
            "maximum": max(deltas),
        },
        "evaluation": {
            "genuine_trials": len(genuine),
            "impostor_trials": len(impostor),
            "observed_eer": eer.balanced_error_rate,
            "false_accept_rate_at_clean_threshold": locked.false_accept_rate,
            "false_reject_rate_at_clean_threshold": locked.false_reject_rate,
        },
    }


def _bandlimit(samples: list[float], sample_rate: int) -> list[float]:
    """Apply deterministic first-order 120 Hz high-pass and 6 kHz low-pass proxies."""
    high_rc = 1.0 / (2.0 * math.pi * 120.0)
    low_rc = 1.0 / (2.0 * math.pi * 6_000.0)
    delta = 1.0 / sample_rate
    high_alpha = high_rc / (high_rc + delta)
    low_alpha = delta / (low_rc + delta)
    high: list[float] = [samples[0]]
    for index in range(1, len(samples)):
        high.append(high_alpha * (high[-1] + samples[index] - samples[index - 1]))
    low: list[float] = [high[0]]
    for value in high[1:]:
        low.append(low[-1] + low_alpha * (value - low[-1]))
    return low


def _add_noise(samples: list[float], snr_db: float, digest: str) -> list[float]:
    signal_rms = math.sqrt(sum(value * value for value in samples) / len(samples))
    noise_rms = signal_rms / (10.0 ** (snr_db / 20.0))
    generator = random.Random(int(digest[:16], 16))
    noise = [generator.gauss(0.0, 1.0) for _ in samples]
    observed = math.sqrt(sum(value * value for value in noise) / len(noise))
    scale = noise_rms / observed
    return [sample + value * scale for sample, value in zip(samples, noise, strict=True)]


def _pcm_wave(audio: AudioBuffer) -> bytes:
    frames = bytearray()
    for sample in audio.samples:
        value = max(-32_768, min(32_767, round(sample * 32_767.0)))
        frames.extend(int(value).to_bytes(2, "little", signed=True))
    destination = io.BytesIO()
    with wave.open(destination, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(audio.sample_rate)
        output.writeframes(bytes(frames))
    return destination.getvalue()


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


if __name__ == "__main__":
    main()
