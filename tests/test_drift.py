from __future__ import annotations

import unittest

from voiceid.domain.drift import DriftBaseline, DriftStatus, evaluate_score_drift


class ScoreDriftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = DriftBaseline(
            model_id="model-v1",
            bin_edges=(0.0, 0.5),
            expected_proportions=(0.25, 0.5, 0.25),
            sample_count=100,
        )

    def test_reports_stable_and_alerting_distributions(self) -> None:
        stable = evaluate_score_drift(
            self.baseline,
            (-0.1,) * 25 + (0.2,) * 50 + (0.8,) * 25,
        )
        shifted = evaluate_score_drift(self.baseline, (0.9,) * 100)

        self.assertEqual(stable.status, DriftStatus.STABLE)
        self.assertAlmostEqual(stable.population_stability_index, 0.0)
        self.assertEqual(shifted.status, DriftStatus.ALERT)

    def test_rejects_bad_baselines_and_small_or_nonfinite_samples(self) -> None:
        with self.assertRaises(ValueError):
            DriftBaseline("model", (0.5, 0.0), (0.2, 0.3, 0.5), 10)
        with self.assertRaises(ValueError):
            evaluate_score_drift(self.baseline, (0.1,) * 10)
        with self.assertRaises(ValueError):
            evaluate_score_drift(
                self.baseline,
                (0.1,) * 29 + (float("nan"),),
            )


if __name__ == "__main__":
    unittest.main()
