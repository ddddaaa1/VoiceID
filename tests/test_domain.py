from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from voiceid.domain.decision import decide
from voiceid.domain.metrics import (
    DetectionCostModel,
    estimate_eer,
    minimum_detection_cost,
    rates_at_threshold,
    wilson_score_interval,
)
from voiceid.domain.models import Decision, QualityReport, VerificationPolicy
from voiceid.domain.scoring import cosine_similarity, robust_voice_template

GOOD_AUDIO = QualityReport(3.2, 0.81, 0.001, 24.0)


class ScoringTests(unittest.TestCase):
    def test_cosine_similarity_is_scale_invariant(self) -> None:
        self.assertAlmostEqual(cosine_similarity((1, 2, 3), (2, 4, 6)), 1.0)

    def test_rejects_non_finite_embeddings(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite"):
            cosine_similarity((1.0, float("nan")), (1.0, 0.0))

    def test_robust_template_rejects_one_outlier(self) -> None:
        template = robust_voice_template([(1.0, 0.05), (0.98, 0.02), (1.0, -0.03), (-1.0, 0.0)])
        self.assertGreater(template[0], 0.99)

    def test_inconsistent_enrollment_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "not mutually consistent"):
            robust_voice_template([(1, 0), (-1, 0), (0, 1)])


class DecisionTests(unittest.TestCase):
    def test_rejects_non_finite_quality_metrics(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite"):
            QualityReport(2.0, 0.8, 0.0, float("nan"))

    def test_genuine_clean_voice_is_accepted(self) -> None:
        result = decide(speaker_score=0.86, spoof_probability=0.08, quality=GOOD_AUDIO)
        self.assertEqual(result.decision, Decision.ACCEPT)

    def test_spoof_overrides_high_speaker_match(self) -> None:
        result = decide(speaker_score=0.95, spoof_probability=0.92, quality=GOOD_AUDIO)
        self.assertEqual(result.decision, Decision.REJECT)
        self.assertIn("suspected_spoof", result.reasons)

    def test_bad_audio_goes_to_review_instead_of_identity_rejection(self) -> None:
        noisy = QualityReport(0.9, 0.2, 0.08, 2.0)
        result = decide(speaker_score=0.2, spoof_probability=0.1, quality=noisy)
        self.assertEqual(result.decision, Decision.REVIEW)
        self.assertIn("insufficient_speech", result.reasons)

    def test_borderline_score_is_reviewed(self) -> None:
        policy = VerificationPolicy(speaker_threshold=0.72, review_margin=0.08)
        result = decide(
            speaker_score=0.68, spoof_probability=0.1, quality=GOOD_AUDIO, policy=policy
        )
        self.assertEqual(result.decision, Decision.REVIEW)


class MetricTests(unittest.TestCase):
    def test_threshold_rates(self) -> None:
        rates = rates_at_threshold([0.9, 0.8, 0.4], [0.7, 0.3, 0.2], 0.75)
        self.assertAlmostEqual(rates.false_reject_rate, 1 / 3)
        self.assertEqual(rates.false_accept_rate, 0.0)

    def test_eer_selects_balanced_operating_point(self) -> None:
        result = estimate_eer([0.9, 0.8, 0.65, 0.4], [0.7, 0.55, 0.3, 0.2])
        self.assertAlmostEqual(result.false_accept_rate, result.false_reject_rate)

    def test_minimum_detection_cost_selects_a_conservative_threshold(self) -> None:
        result = minimum_detection_cost(
            [0.9, 0.8],
            [0.7, 0.2],
            DetectionCostModel(target_probability=0.01),
        )
        self.assertEqual(result.rates.threshold, 0.8)
        self.assertEqual(result.normalized_cost, 0.0)

    def test_metrics_reject_non_finite_scores(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite"):
            rates_at_threshold([0.9, float("nan")], [0.2], 0.5)

    def test_wilson_interval_does_not_claim_zero_risk_after_zero_errors(self) -> None:
        no_false_accepts = wilson_score_interval(0, 30)
        one_false_reject = wilson_score_interval(1, 30)

        self.assertEqual(no_false_accepts.lower, 0.0)
        self.assertAlmostEqual(no_false_accepts.upper, 0.1135, places=4)
        self.assertAlmostEqual(one_false_reject.lower, 0.0059, places=4)
        self.assertAlmostEqual(one_false_reject.upper, 0.1667, places=4)

    def test_wilson_interval_rejects_invalid_counts_and_confidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "integer counts"):
            wilson_score_interval(2, 1)
        with self.assertRaisesRegex(ValueError, "confidence_level"):
            wilson_score_interval(0, 1, 1.0)


if __name__ == "__main__":
    unittest.main()
