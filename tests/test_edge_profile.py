from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from voiceid.adapters.models.edge_onnx import (
    EdgeArtifactError,
    OnnxEcapaRuntime,
    load_edge_artifact_manifest,
)
from voiceid.domain.edge_profile import EdgeProfileError, load_edge_profile

REPOSITORY_ROOT = Path(__file__).parents[1]
PROFILE = REPOSITORY_ROOT / "config/edge-profile-v1.json"


class EdgeProfileTests(unittest.TestCase):
    def test_versioned_profile_preserves_product_and_evidence_budgets(self) -> None:
        profile = load_edge_profile(PROFILE)

        self.assertEqual(profile.profile_id, "voiceid-phone-arm-int8-v1")
        self.assertEqual(profile.target_class, "phone-class-arm64-cpu")
        self.assertEqual(profile.sample_rate, 16_000)
        self.assertEqual(profile.budgets.artifact_size_mib, 32.0)
        self.assertEqual(profile.fidelity.minimum_embedding_cosine, 0.98)

    def test_profile_rejects_disabled_hardware_evidence_boundary(self) -> None:
        payload = json.loads(PROFILE.read_text(encoding="utf-8"))
        payload["measurement_policy"]["hardware_specific"] = False
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "profile.json"
            candidate.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(EdgeProfileError, "evidence boundaries"):
                load_edge_profile(candidate)


class EdgeArtifactManifestTests(unittest.TestCase):
    def test_manifest_verifies_artifact_size_and_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fp32 = root / "fp32.onnx"
            int8 = root / "int8.onnx"
            fp32.write_bytes(b"fp32-model")
            int8.write_bytes(b"int8-model")
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(_manifest_payload(fp32, int8)), encoding="utf-8")

            manifest = load_edge_artifact_manifest(manifest_path)

            self.assertEqual(manifest.embedding_dimension, 192)
            self.assertEqual(manifest.int8.path, int8.resolve())

    def test_manifest_rejects_artifact_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fp32 = root / "fp32.onnx"
            int8 = root / "int8.onnx"
            fp32.write_bytes(b"fp32-model")
            int8.write_bytes(b"int8-model")
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(_manifest_payload(fp32, int8)), encoding="utf-8")
            int8.write_bytes(b"tampered!!")

            with self.assertRaisesRegex(EdgeArtifactError, "integrity"):
                load_edge_artifact_manifest(manifest_path)

    def test_runtime_rejects_a_manifest_for_another_source_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fp32 = root / "fp32.onnx"
            int8 = root / "int8.onnx"
            fp32.write_bytes(b"fp32-model")
            int8.write_bytes(b"int8-model")
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(_manifest_payload(fp32, int8)), encoding="utf-8")

            with self.assertRaisesRegex(EdgeArtifactError, "incompatible"):
                OnnxEcapaRuntime(manifest_path).encode([0.0] * 8_000)


def _manifest_payload(fp32: Path, int8: Path) -> dict[str, object]:
    return {
        "schema_version": "voiceid-edge-artifact/v1",
        "artifact_id": "test-edge-v1",
        "source_model_id": "test-model@revision",
        "created_at": "2026-08-26T00:00:00Z",
        "input": {
            "name": "waveform",
            "dtype": "float32",
            "shape": ["batch", "samples"],
            "sample_rate": 16_000,
            "min_samples": 8_000,
            "max_samples": 240_000,
        },
        "output": {
            "name": "embedding",
            "dtype": "float32",
            "shape": ["batch", 192],
            "l2_normalized": True,
        },
        "quantization": {
            "format": "QDQ",
            "activation_type": "uint8",
            "weight_type": "int8",
            "calibration_method": "minmax",
            "operators": ["Conv"],
            "calibration_manifest_sha256": "a" * 64,
            "calibration_items": 2,
        },
        "artifacts": {
            "fp32": _artifact(fp32),
            "int8": _artifact(int8),
        },
        "toolchain": {"onnxruntime": "test"},
    }


def _artifact(path: Path) -> dict[str, object]:
    return {
        "path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }


if __name__ == "__main__":
    unittest.main()
