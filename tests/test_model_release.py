from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from voiceid.adapters.models.release_registry import ModelReleaseError, verify_model_release

REPOSITORY_ROOT = Path(__file__).parents[1]
RELEASE = REPOSITORY_ROOT / "model-registry/releases/voiceid-research-2026-08-25.json"


class ModelReleaseTests(unittest.TestCase):
    def test_frozen_release_matches_runtime_and_local_hashes(self) -> None:
        release = verify_model_release(RELEASE, REPOSITORY_ROOT)

        self.assertEqual(release.status, "experimental")
        self.assertEqual(release.verified_local_artifacts, 1)
        self.assertEqual(release.verified_evidence, 1)

    def test_rejects_countermeasure_enablement_and_hash_tampering(self) -> None:
        payload = json.loads(RELEASE.read_text(encoding="utf-8"))
        payload["models"][1]["deployment_enabled"] = True
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "release.json"
            candidate.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ModelReleaseError):
                verify_model_release(candidate, REPOSITORY_ROOT)

        payload["models"][1]["deployment_enabled"] = False
        payload["models"][1]["artifacts"][0]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "release.json"
            candidate.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ModelReleaseError, "integrity"):
                verify_model_release(candidate, REPOSITORY_ROOT)

    def test_rejects_source_revision_tampering(self) -> None:
        payload = json.loads(RELEASE.read_text(encoding="utf-8"))
        payload["models"][0]["source_revision"] = "0" * 40
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "release.json"
            candidate.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ModelReleaseError, "source revision"):
                verify_model_release(candidate, REPOSITORY_ROOT)


if __name__ == "__main__":
    unittest.main()
