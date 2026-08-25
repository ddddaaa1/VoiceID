"""Export the pinned full-waveform ECAPA graph and calibrate an INT8 ONNX artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from voiceid.adapters.audio.energy_vad import EnergyVoiceActivityDetector
from voiceid.adapters.audio.wave_decoder import PcmWaveDecoder
from voiceid.adapters.evaluation.json_audio_manifest import load_audio_trial_manifest
from voiceid.adapters.models.speechbrain_ecapa import (
    SpeechBrainEcapaEmbedder,
    SpeechBrainRuntime,
)
from voiceid.application.preprocessing import AudioPreprocessor
from voiceid.domain.evaluation import TrialPartition

MIN_SAMPLES = 8_000
MAX_SAMPLES = 240_000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/raw/librispeech/voiceid-clean-v1/audio-trials.json"),
        help="Hashed audio manifest used only for development-partition calibration",
    )
    parser.add_argument(
        "--audio-root",
        type=Path,
        default=Path("data/raw/librispeech/voiceid-clean-v1"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/edge/ecapa-tdnn-onnx-int8-v1"),
    )
    parser.add_argument(
        "--provenance-output",
        type=Path,
        default=Path("experiments/edge-ecapa-int8-v1/artifact-provenance.json"),
        help="Non-model artifact metadata safe to commit",
    )
    parser.add_argument("--calibration-items", type=int, default=24)
    parser.add_argument("--force", action="store_true")
    arguments = parser.parse_args()

    if arguments.calibration_items <= 0:
        parser.error("calibration-items must be positive")
    output_dir = arguments.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()) and not arguments.force:
        parser.error("output directory is not empty; pass --force to replace generated artifacts")

    manifest = load_audio_trial_manifest(arguments.manifest)
    references = sorted(
        {
            (sample.path, sample.sha256)
            for enrollment in manifest.enrollments
            if enrollment.partition is TrialPartition.DEVELOPMENT
            for sample in enrollment.samples
        }
    )[: arguments.calibration_items]
    if len(references) < arguments.calibration_items:
        parser.error("the development partition does not contain enough calibration samples")
    waveforms = [
        _preprocessed_speech(arguments.audio_root / relative, digest)
        for relative, digest in references
    ]

    with tempfile.TemporaryDirectory(prefix="voiceid-edge-export-") as directory:
        temporary = Path(directory)
        fp32_raw = temporary / "ecapa.fp32.raw.onnx"
        fp32 = temporary / "ecapa.fp32.onnx"
        int8 = temporary / "ecapa.int8.onnx"
        toolchain = _export_and_quantize(waveforms, fp32_raw, fp32, int8)

        output_dir.mkdir(parents=True, exist_ok=True)
        destinations = {
            "fp32": output_dir / fp32.name,
            "int8": output_dir / int8.name,
        }
        for source, destination in ((fp32, destinations["fp32"]), (int8, destinations["int8"])):
            shutil.copy2(source, destination)

    payload = {
        "schema_version": "voiceid-edge-artifact/v1",
        "artifact_id": "ecapa-tdnn-onnx-int8-v1",
        "source_model_id": SpeechBrainEcapaEmbedder.MODEL_ID,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "input": {
            "name": "waveform",
            "dtype": "float32",
            "shape": ["batch", "samples"],
            "sample_rate": SpeechBrainEcapaEmbedder.EXPECTED_SAMPLE_RATE,
            "min_samples": MIN_SAMPLES,
            "max_samples": MAX_SAMPLES,
        },
        "output": {
            "name": "embedding",
            "dtype": "float32",
            "shape": ["batch", SpeechBrainEcapaEmbedder.EXPECTED_DIMENSION],
            "l2_normalized": True,
        },
        "quantization": {
            "format": "QDQ",
            "activation_type": "uint8",
            "weight_type": "int8",
            "calibration_method": "minmax",
            "operators": ["Conv"],
            "calibration_manifest_sha256": _sha256(arguments.manifest),
            "calibration_items": len(waveforms),
        },
        "artifacts": {
            name: {
                "path": path.name,
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for name, path in destinations.items()
        },
        "toolchain": toolchain,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")
    provenance = {
        "schema_version": "voiceid-edge-artifact-provenance/v1",
        "artifact_id": payload["artifact_id"],
        "source_model_id": payload["source_model_id"],
        "created_at": payload["created_at"],
        "input": payload["input"],
        "output": payload["output"],
        "quantization": payload["quantization"],
        "artifacts": {
            name: {
                "sha256": metadata["sha256"],
                "size_bytes": metadata["size_bytes"],
                "repository_committed": False,
            }
            for name, metadata in payload["artifacts"].items()
        },
        "toolchain": payload["toolchain"],
    }
    arguments.provenance_output.parent.mkdir(parents=True, exist_ok=True)
    arguments.provenance_output.write_text(
        f"{json.dumps(provenance, indent=2, sort_keys=True)}\n", encoding="utf-8"
    )
    print(f"manifest={manifest_path}")
    print(f"provenance={arguments.provenance_output}")
    print(f"fp32_mib={destinations['fp32'].stat().st_size / 1_048_576:.3f}")
    print(f"int8_mib={destinations['int8'].stat().st_size / 1_048_576:.3f}")
    print(f"calibration_items={len(waveforms)}")


def _export_and_quantize(
    waveforms: list[list[float]], fp32_raw: Path, fp32: Path, int8: Path
) -> dict[str, str]:
    import numpy
    import onnx
    import onnxruntime
    import onnxscript
    import speechbrain
    import torch
    from onnxruntime.quantization import (
        CalibrationDataReader,
        CalibrationMethod,
        QuantFormat,
        QuantType,
        quantize_static,
    )
    from onnxruntime.quantization.shape_inference import quant_pre_process

    class FullWaveformEcapa(torch.nn.Module):
        def __init__(self, classifier: object) -> None:
            super().__init__()
            self.features = classifier.mods.compute_features
            self.normalization = classifier.mods.mean_var_norm
            self.embedding_model = classifier.mods.embedding_model

        def forward(self, waveform: object) -> object:
            lengths = torch.ones((waveform.shape[0],), device=waveform.device)
            features = self.normalization(self.features(waveform), lengths)
            embedding = self.embedding_model(features, lengths).squeeze(1)
            return torch.nn.functional.normalize(embedding, p=2, dim=1)

    runtime = SpeechBrainRuntime(
        source=SpeechBrainEcapaEmbedder.MODEL_SOURCE,
        revision=SpeechBrainEcapaEmbedder.MODEL_REVISION,
        cache_dir=Path("artifacts/models/spkrec-ecapa-voxceleb"),
        device="cpu",
    )
    runtime._ensure_loaded()  # The export tool intentionally accesses the loaded upstream module.
    model = FullWaveformEcapa(runtime._classifier).eval()
    example = torch.tensor(waveforms[0][:48_000], dtype=torch.float32).unsqueeze(0)
    torch.onnx.export(
        model,
        (example,),
        fp32_raw,
        input_names=["waveform"],
        output_names=["embedding"],
        opset_version=18,
        dynamo=True,
        external_data=False,
        dynamic_shapes={
            "waveform": {
                1: torch.export.Dim("samples", min=MIN_SAMPLES, max=MAX_SAMPLES),
            }
        },
        verify=False,
    )
    quant_pre_process(
        str(fp32_raw),
        str(fp32),
        skip_symbolic_shape=True,
        skip_optimization=False,
        skip_onnx_shape=False,
    )

    arrays = [numpy.asarray(waveform, dtype=numpy.float32)[None, :] for waveform in waveforms]

    class Reader(CalibrationDataReader):
        def __init__(self) -> None:
            self._iterator = iter({"waveform": waveform} for waveform in arrays)

        def get_next(self) -> dict[str, object] | None:
            return next(self._iterator, None)

    quantize_static(
        str(fp32),
        str(int8),
        Reader(),
        quant_format=QuantFormat.QDQ,
        activation_type=QuantType.QUInt8,
        weight_type=QuantType.QInt8,
        calibrate_method=CalibrationMethod.MinMax,
        per_channel=True,
        op_types_to_quantize=["Conv"],
    )
    exported_outputs: dict[str, object] = {}
    for path in (fp32, int8):
        onnx.checker.check_model(onnx.load(path))
        session = onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        output = session.run(["embedding"], {"waveform": arrays[0]})[0]
        if output.shape != (1, SpeechBrainEcapaEmbedder.EXPECTED_DIMENSION):
            raise RuntimeError(f"export validation returned an invalid shape for {path.name}")
        exported_outputs[path.name] = output.reshape(-1)
    with torch.inference_mode():
        reference = model(torch.from_numpy(arrays[0])).detach().cpu().numpy().reshape(-1)
    fp32_cosine = float(
        numpy.dot(reference, exported_outputs[fp32.name])
        / (numpy.linalg.norm(reference) * numpy.linalg.norm(exported_outputs[fp32.name]))
    )
    int8_cosine = float(
        numpy.dot(reference, exported_outputs[int8.name])
        / (numpy.linalg.norm(reference) * numpy.linalg.norm(exported_outputs[int8.name]))
    )
    if fp32_cosine < 0.9999 or int8_cosine < 0.98:
        raise RuntimeError("exported model failed the embedding fidelity gate")
    return {
        "torch": torch.__version__,
        "speechbrain": speechbrain.__version__,
        "onnx": onnx.__version__,
        "onnxruntime": onnxruntime.__version__,
        "onnxscript": onnxscript.__version__,
        "opset": "18",
        "pytorch_fp32_cosine": f"{fp32_cosine:.9f}",
        "pytorch_int8_cosine": f"{int8_cosine:.9f}",
    }


def _preprocessed_speech(path: Path, expected_digest: str) -> list[float]:
    if _sha256(path) != expected_digest:
        raise ValueError(f"calibration audio failed integrity verification: {path.name}")
    result = AudioPreprocessor(PcmWaveDecoder(), EnergyVoiceActivityDetector()).process(
        path.read_bytes()
    )
    samples = [
        sample
        for segment in result.processed.speech_segments
        for sample in result.processed.audio.samples[segment.start_sample : segment.end_sample]
    ]
    if not MIN_SAMPLES <= len(samples) <= MAX_SAMPLES:
        raise ValueError(f"calibration audio is outside the edge input bounds: {path.name}")
    return samples


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
