from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
EXPERIMENT = ROOT / "experiments/edge-ecapa-int8-v1"


class FrozenEdgeEvidenceTests(unittest.TestCase):
    def test_benchmark_is_bound_to_public_artifact_provenance(self) -> None:
        provenance = json.loads(
            (EXPERIMENT / "artifact-provenance.json").read_text(encoding="utf-8")
        )
        benchmark = json.loads((EXPERIMENT / "arm64-benchmark.json").read_text(encoding="utf-8"))

        self.assertEqual(provenance["schema_version"], "voiceid-edge-artifact-provenance/v1")
        self.assertEqual(benchmark["schema_version"], "voiceid-edge-benchmark/v1")
        self.assertEqual(provenance["artifact_id"], benchmark["artifact_id"])
        for variant in ("fp32", "int8"):
            self.assertEqual(
                provenance["artifacts"][variant]["sha256"],
                benchmark["artifacts"][f"{variant}_sha256"],
            )
            self.assertFalse(provenance["artifacts"][variant]["repository_committed"])
        self.assertEqual(benchmark["host"]["machine"], "arm64")
        self.assertTrue(benchmark["all_locally_measurable_budgets_pass"])
        self.assertIn("phone hardware", benchmark["scope"]["not_measured"])

    def test_channel_report_preserves_proxy_and_privacy_boundaries(self) -> None:
        report = json.loads((EXPERIMENT / "channel-proxy-report.json").read_text(encoding="utf-8"))

        self.assertEqual(report["schema_version"], "voiceid-edge-channel-evaluation/v1")
        self.assertFalse(report["protocol"]["raw_audio_published"])
        self.assertFalse(report["protocol"]["per_trial_scores_published"])
        self.assertIn("bandlimited_noise_10db_proxy", report["conditions"])
        self.assertTrue(any("not recordings" in item for item in report["limitations"]))


if __name__ == "__main__":
    unittest.main()
