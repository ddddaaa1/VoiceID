from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from voiceid.adapters.evaluation.json_manifest import ManifestFormatError
from voiceid.adapters.evaluation.json_spoof_manifest import (
    load_spoof_score_manifest,
    spoof_evaluation_report_payload,
    write_spoof_evaluation_report,
)
from voiceid.application.spoof_evaluation import evaluate_spoof_scores
from voiceid.domain.evaluation import TrialPartition
from voiceid.domain.spoof_metrics import (
    CountermeasureCostModel,
    countermeasure_rates,
    estimate_countermeasure_eer,
    minimum_countermeasure_cost,
)
from voiceid.domain.spoofing import (
    AttackCategory,
    SpoofLabel,
    SpoofProtocolError,
    SpoofScoreManifest,
    SpoofScoreTrial,
)

EXAMPLE = (
    Path(__file__).parents[1]
    / "examples"
    / "evaluation"
    / "spoof-scores.example.json"
)


def trial(
    trial_id: str,
    partition: TrialPartition,
    speaker_id: str,
    label: SpoofLabel,
    probability: float,
    category: AttackCategory | None = None,
) -> SpoofScoreTrial:
    attack_category = category or (
        AttackCategory.BONAFIDE
        if label is SpoofLabel.BONAFIDE
        else AttackCategory.SYNTHETIC
    )
    return SpoofScoreTrial(
        trial_id=trial_id,
        partition=partition,
        speaker_id=speaker_id,
        label=label,
        attack_category=attack_category,
        attack_id="bonafide" if label is SpoofLabel.BONAFIDE else "A01",
        spoof_probability=probability,
        condition="clean",
    )


class CountermeasureMetricTests(unittest.TestCase):
    def test_threshold_direction_and_error_rates(self) -> None:
        rates = countermeasure_rates([0.1, 0.7], [0.4, 0.9], 0.6)
        self.assertEqual(rates.bonafide_reject_rate, 0.5)
        self.assertEqual(rates.spoof_accept_rate, 0.5)
        self.assertEqual(rates.bonafide_rejects, 1)
        self.assertEqual(rates.spoof_accepts, 1)

    def test_eer_and_minimum_cost_are_selected_from_observed_scores(self) -> None:
        bonafide = [0.1, 0.2, 0.7, 0.8]
        spoof = [0.3, 0.4, 0.9, 1.0]
        eer = estimate_countermeasure_eer(bonafide, spoof)
        minimum = minimum_countermeasure_cost(
            bonafide,
            spoof,
            CountermeasureCostModel(spoof_prior=0.5),
        )
        self.assertEqual(eer.bonafide_reject_rate, eer.spoof_accept_rate)
        self.assertEqual(minimum.normalized_cost, 0.5)

    def test_rejects_invalid_probabilities_and_costs(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            countermeasure_rates([0.1], [1.1], 0.5)
        with self.assertRaisesRegex(ValueError, "threshold"):
            countermeasure_rates([0.1], [0.9], -0.1)
        with self.assertRaisesRegex(ValueError, "spoof_prior"):
            CountermeasureCostModel(spoof_prior=1.0)


class SpoofProtocolTests(unittest.TestCase):
    def test_rejects_label_category_conflicts(self) -> None:
        with self.assertRaisesRegex(SpoofProtocolError, "bonafide category"):
            trial(
                "bad",
                TrialPartition.DEVELOPMENT,
                "dev-a",
                SpoofLabel.BONAFIDE,
                0.1,
                AttackCategory.REPLAY,
            )

    def test_rejects_speaker_leakage(self) -> None:
        trials = (
            trial("d-b", TrialPartition.DEVELOPMENT, "shared", SpoofLabel.BONAFIDE, 0.1),
            trial("d-s", TrialPartition.DEVELOPMENT, "dev-b", SpoofLabel.SPOOF, 0.9),
            trial("e-b", TrialPartition.EVALUATION, "shared", SpoofLabel.BONAFIDE, 0.1),
            trial("e-s", TrialPartition.EVALUATION, "eval-b", SpoofLabel.SPOOF, 0.9),
        )
        with self.assertRaisesRegex(SpoofProtocolError, "speaker leakage"):
            SpoofScoreManifest("dataset", "1", "model", "pipeline", trials)


class SpoofEvaluationTests(unittest.TestCase):
    def test_locks_development_threshold_and_breaks_down_attacks(self) -> None:
        manifest = load_spoof_score_manifest(EXAMPLE)
        report = evaluate_spoof_scores(manifest)

        self.assertEqual(report.selected_threshold, 0.65)
        self.assertEqual(report.evaluation.rates_at_selected_threshold.spoof_accepts, 1)
        self.assertEqual(
            report.evaluation.rates_at_selected_threshold.spoof_accept_rate, 0.25
        )
        replay = next(
            attack
            for attack in report.evaluation_attacks
            if attack.attack_category is AttackCategory.REPLAY
        )
        self.assertEqual(replay.spoof_accepts, 1)
        self.assertEqual(replay.spoof_trials, 2)
        self.assertGreater(replay.spoof_accept_interval.upper, 0.5)

    def test_strict_json_round_trip_and_unknown_field_rejection(self) -> None:
        manifest = load_spoof_score_manifest(EXAMPLE)
        report = evaluate_spoof_scores(manifest)
        payload = spoof_evaluation_report_payload(report)
        self.assertEqual(
            payload["calibration"]["score_semantics"],
            "higher_is_more_likely_spoof",
        )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            write_spoof_evaluation_report(report, output)
            self.assertEqual(json.loads(output.read_text()), payload)

            invalid = json.loads(EXAMPLE.read_text())
            invalid["unexpected"] = True
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(invalid), encoding="utf-8")
            with self.assertRaisesRegex(ManifestFormatError, "unknown: unexpected"):
                load_spoof_score_manifest(path)


if __name__ == "__main__":
    unittest.main()
