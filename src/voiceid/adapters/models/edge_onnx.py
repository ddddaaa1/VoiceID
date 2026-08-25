"""Integrity-checked ONNX Runtime adapter for exported ECAPA models."""

from __future__ import annotations

import hashlib
import importlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from voiceid.adapters.models.speechbrain_ecapa import (
    SpeakerEmbeddingError,
    SpeechBrainEcapaEmbedder,
)


class EdgeArtifactError(SpeakerEmbeddingError):
    """Raised when an edge artifact or its manifest cannot be trusted."""


@dataclass(frozen=True, slots=True)
class EdgeArtifact:
    path: Path
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class EdgeArtifactManifest:
    artifact_id: str
    source_model_id: str
    sample_rate: int
    min_samples: int
    max_samples: int
    embedding_dimension: int
    fp32: EdgeArtifact
    int8: EdgeArtifact


def load_edge_artifact_manifest(path: Path) -> EdgeArtifactManifest:
    """Load a strict manifest and verify both local model artifacts."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EdgeArtifactError("edge artifact manifest is unavailable or invalid") from error
    root = _object(payload, "manifest")
    _exact(
        root,
        {
            "schema_version",
            "artifact_id",
            "source_model_id",
            "created_at",
            "input",
            "output",
            "quantization",
            "artifacts",
            "toolchain",
        },
        "manifest",
    )
    if root["schema_version"] != "voiceid-edge-artifact/v1":
        raise EdgeArtifactError("unsupported edge artifact schema")

    input_contract = _object(root["input"], "input")
    _exact(
        input_contract,
        {"name", "dtype", "shape", "sample_rate", "min_samples", "max_samples"},
        "input",
    )
    if input_contract["name"] != "waveform" or input_contract["dtype"] != "float32":
        raise EdgeArtifactError("unsupported edge input tensor")
    if input_contract["shape"] != ["batch", "samples"]:
        raise EdgeArtifactError("unsupported edge input shape")
    sample_rate = _positive_int(input_contract["sample_rate"], "input.sample_rate")
    min_samples = _positive_int(input_contract["min_samples"], "input.min_samples")
    max_samples = _positive_int(input_contract["max_samples"], "input.max_samples")
    if min_samples >= max_samples:
        raise EdgeArtifactError("edge input sample bounds are invalid")

    output_contract = _object(root["output"], "output")
    _exact(output_contract, {"name", "dtype", "shape", "l2_normalized"}, "output")
    dimension = _positive_int(
        output_contract["shape"][-1]
        if isinstance(output_contract["shape"], list) and output_contract["shape"]
        else None,
        "output.shape",
    )
    if (
        output_contract["name"] != "embedding"
        or output_contract["dtype"] != "float32"
        or output_contract["shape"] != ["batch", dimension]
        or output_contract["l2_normalized"] is not True
    ):
        raise EdgeArtifactError("unsupported edge output tensor")

    quantization = _object(root["quantization"], "quantization")
    _exact(
        quantization,
        {
            "format",
            "activation_type",
            "weight_type",
            "calibration_method",
            "operators",
            "calibration_manifest_sha256",
            "calibration_items",
        },
        "quantization",
    )
    if (
        quantization["format"] != "QDQ"
        or quantization["activation_type"] != "uint8"
        or quantization["weight_type"] != "int8"
        or quantization["calibration_method"] != "minmax"
        or quantization["operators"] != ["Conv"]
    ):
        raise EdgeArtifactError("unsupported edge quantization contract")
    _digest(quantization["calibration_manifest_sha256"], "calibration manifest")
    _positive_int(quantization["calibration_items"], "calibration_items")

    artifacts = _object(root["artifacts"], "artifacts")
    _exact(artifacts, {"fp32", "int8"}, "artifacts")
    base = path.resolve().parent
    fp32 = _artifact(artifacts["fp32"], base, "fp32")
    int8 = _artifact(artifacts["int8"], base, "int8")

    _string(root["artifact_id"], "artifact_id")
    _string(root["source_model_id"], "source_model_id")
    _string(root["created_at"], "created_at")
    _object(root["toolchain"], "toolchain")
    return EdgeArtifactManifest(
        artifact_id=str(root["artifact_id"]),
        source_model_id=str(root["source_model_id"]),
        sample_rate=sample_rate,
        min_samples=min_samples,
        max_samples=max_samples,
        embedding_dimension=dimension,
        fp32=fp32,
        int8=int8,
    )


class OnnxEcapaRuntime:
    """Run a hash-verified, full-waveform ECAPA graph with ONNX Runtime."""

    def __init__(
        self,
        manifest_path: Path | str,
        *,
        variant: str = "int8",
        intra_op_threads: int = 1,
    ) -> None:
        if variant not in {"fp32", "int8"}:
            raise ValueError("edge artifact variant must be 'fp32' or 'int8'")
        if intra_op_threads <= 0:
            raise ValueError("intra_op_threads must be positive")
        self._manifest_path = Path(manifest_path)
        self._variant = variant
        self._intra_op_threads = intra_op_threads
        self._manifest: EdgeArtifactManifest | None = None
        self._session: Any | None = None

    def encode(self, samples: list[float] | tuple[float, ...]) -> list[float]:
        self._ensure_loaded()
        assert self._manifest is not None
        assert self._session is not None
        if not self._manifest.min_samples <= len(samples) <= self._manifest.max_samples:
            raise EdgeArtifactError("waveform length is outside the exported edge contract")
        if any(not math.isfinite(float(sample)) or abs(float(sample)) > 1.0 for sample in samples):
            raise EdgeArtifactError("waveform contains invalid samples")
        try:
            numpy = importlib.import_module("numpy")
            waveform = numpy.asarray(samples, dtype=numpy.float32)[None, :]
            result = self._session.run(["embedding"], {"waveform": waveform})[0]
            embedding = [float(value) for value in result.reshape(-1)]
        except EdgeArtifactError:
            raise
        except Exception as error:
            raise EdgeArtifactError("ONNX ECAPA inference failed") from error
        if len(embedding) != self._manifest.embedding_dimension or any(
            not math.isfinite(value) for value in embedding
        ):
            raise EdgeArtifactError("ONNX ECAPA returned an invalid embedding")
        return embedding

    def _ensure_loaded(self) -> None:
        if self._session is not None:
            return
        manifest = load_edge_artifact_manifest(self._manifest_path)
        if (
            manifest.source_model_id != SpeechBrainEcapaEmbedder.MODEL_ID
            or manifest.sample_rate != SpeechBrainEcapaEmbedder.EXPECTED_SAMPLE_RATE
            or manifest.embedding_dimension != SpeechBrainEcapaEmbedder.EXPECTED_DIMENSION
        ):
            raise EdgeArtifactError("edge artifact is incompatible with the ECAPA adapter")
        artifact = manifest.int8 if self._variant == "int8" else manifest.fp32
        try:
            ort = importlib.import_module("onnxruntime")
        except ImportError as error:
            raise EdgeArtifactError(
                "ONNX Runtime is missing; install the project with the 'edge' extra"
            ) from error
        options = ort.SessionOptions()
        options.intra_op_num_threads = self._intra_op_threads
        options.inter_op_num_threads = 1
        try:
            self._session = ort.InferenceSession(
                str(artifact.path),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        except Exception as error:
            raise EdgeArtifactError("ONNX ECAPA session could not be created") from error
        self._manifest = manifest


def _artifact(value: object, base: Path, name: str) -> EdgeArtifact:
    item = _object(value, f"artifacts.{name}")
    _exact(item, {"path", "sha256", "size_bytes"}, f"artifacts.{name}")
    relative = Path(_string(item["path"], f"artifacts.{name}.path"))
    if relative.is_absolute() or ".." in relative.parts:
        raise EdgeArtifactError("edge artifact paths must stay beside the manifest")
    path = (base / relative).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise EdgeArtifactError(f"{name} edge artifact is unavailable")
    expected_size = _positive_int(item["size_bytes"], f"artifacts.{name}.size_bytes")
    if path.stat().st_size != expected_size:
        raise EdgeArtifactError(f"{name} edge artifact size does not match its manifest")
    digest = _digest(item["sha256"], f"artifacts.{name}.sha256")
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise EdgeArtifactError(f"{name} edge artifact failed integrity verification")
    return EdgeArtifact(path=path, sha256=digest, size_bytes=expected_size)


def _object(value: object, location: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise EdgeArtifactError(f"{location} must be an object")
    return value


def _exact(value: dict[str, object], fields: set[str], location: str) -> None:
    if set(value) != fields:
        raise EdgeArtifactError(f"{location} fields are invalid")


def _string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise EdgeArtifactError(f"{location} must be a non-empty string")
    return value


def _positive_int(value: object, location: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise EdgeArtifactError(f"{location} must be a positive integer")
    return value


def _digest(value: object, location: str) -> str:
    digest = _string(value, location)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise EdgeArtifactError(f"{location} must be lowercase SHA-256")
    return digest
