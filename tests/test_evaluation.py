from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from voiceid.adapters.evaluation.json_manifest import (
    ManifestFormatError,
    evaluation_report_payload,
    load_scored_trial_manifest,
)
from voiceid.application.evaluation import evaluate_scored_trials
from voiceid.domain.evaluation import (
    EvaluationProtocolError,
    ScoredTrial,
    ScoredTrialManifest,
    TrialLabel,
    TrialPartition,
)


def trial(
    trial_id: str,
    partition: TrialPartition,
    enrollment_speaker: str,
    probe_speaker: str,
    score: float,
    *,
    condition: str = "clean",
) -> ScoredTrial:
    label = (
        TrialLabel.GENUINE
        if enrollment_speaker == probe_speaker
        else TrialLabel.IMPOSTOR
    )
    return ScoredTrial(
        trial_id=trial_id,
        partition=partition,
        label=label,
        enrollment_speaker_id=enrollment_speaker,
        probe_speaker_id=probe_speaker,
        score=score,
        condition=condition,
    )


def valid_manifest() -> ScoredTrialManifest:
    return ScoredTrialManifest(
        dataset_id="test-corpus",
        dataset_version="1",
        model_id="fake-encoder-v1",
        pipeline_id="fake-pipeline-v1",
        trials=(
            trial("dev-g-1", TrialPartition.DEVELOPMENT, "dev-a", "dev-a", 0.90),
            trial("dev-g-2", TrialPartition.DEVELOPMENT, "dev-b", "dev-b", 0.80),
            trial("dev-i-1", TrialPartition.DEVELOPMENT, "dev-a", "dev-b", 0.70),
            trial("dev-i-2", TrialPartition.DEVELOPMENT, "dev-b", "dev-a", 0.20),
            trial("eval-g-1", TrialPartition.EVALUATION, "eval-c", "eval-c", 0.85),
            trial("eval-g-2", TrialPartition.EVALUATION, "eval-d", "eval-d", 0.75),
            trial("eval-i-1", TrialPartition.EVALUATION, "eval-c", "eval-d", 0.72),
            trial("eval-i-2", TrialPartition.EVALUATION, "eval-d", "eval-c", 0.10),
        ),
    )


class EvaluationProtocolTests(unittest.TestCase):
    def test_calibrates_on_development_and_locks_threshold_for_evaluation(self) -> None:
        report = evaluate_scored_trials(valid_manifest())

        self.assertEqual(report.threshold_source, "development_min_dcf")
        self.assertEqual(report.selected_threshold, 0.80)
        self.assertEqual(
            report.development.rates_at_selected_threshold.false_reject_rate, 0.0
        )
        self.assertEqual(
            report.evaluation.rates_at_selected_threshold.false_reject_rate, 0.5
        )
        self.assertEqual(report.evaluation.rates_at_selected_threshold.threshold, 0.80)
        self.assertEqual(report.evaluation.minimum_dcf.rates.threshold, 0.75)
        self.assertEqual(report.schema_version, "voiceid-evaluation-report/v2")
        self.assertGreater(report.evaluation.false_accept_interval.upper, 0.0)

    def test_rejects_speaker_leakage_between_partitions(self) -> None:
        trials = list(valid_manifest().trials)
        trials[4] = trial(
            "eval-g-1", TrialPartition.EVALUATION, "dev-a", "dev-a", 0.85
        )
        with self.assertRaisesRegex(EvaluationProtocolError, "speaker leakage"):
            ScoredTrialManifest(
                dataset_id="leaked",
                dataset_version="1",
                model_id="fake",
                pipeline_id="fake",
                trials=tuple(trials),
            )

    def test_rejects_a_label_that_conflicts_with_speaker_ids(self) -> None:
        with self.assertRaisesRegex(EvaluationProtocolError, "label conflicts"):
            ScoredTrial(
                trial_id="bad-label",
                partition=TrialPartition.DEVELOPMENT,
                label=TrialLabel.GENUINE,
                enrollment_speaker_id="speaker-a",
                probe_speaker_id="speaker-b",
                score=0.8,
            )

    def test_condition_without_both_classes_is_reported_without_inventing_rates(self) -> None:
        manifest = valid_manifest()
        trials = tuple(
            ScoredTrial(
                trial_id=item.trial_id,
                partition=item.partition,
                label=item.label,
                enrollment_speaker_id=item.enrollment_speaker_id,
                probe_speaker_id=item.probe_speaker_id,
                score=item.score,
                condition="genuine-only" if item.trial_id == "eval-g-1" else "clean",
            )
            for item in manifest.trials
        )
        report = evaluate_scored_trials(
            ScoredTrialManifest(
                dataset_id=manifest.dataset_id,
                dataset_version=manifest.dataset_version,
                model_id=manifest.model_id,
                pipeline_id=manifest.pipeline_id,
                trials=trials,
            )
        )
        isolated = next(
            item for item in report.evaluation_conditions if item.condition == "genuine-only"
        )
        self.assertIsNone(isolated.rates_at_selected_threshold)


class JsonManifestAdapterTests(unittest.TestCase):
    def test_loads_the_versioned_example_and_serializes_a_report(self) -> None:
        example = (
            Path(__file__).parents[1]
            / "examples"
            / "evaluation"
            / "scored-trials.example.json"
        )
        manifest = load_scored_trial_manifest(example)
        payload = evaluation_report_payload(evaluate_scored_trials(manifest))

        self.assertEqual(manifest.dataset_id, "synthetic-contract-example")
        self.assertEqual(len(manifest.trials), 16)
        self.assertEqual(payload["calibration"]["threshold_source"], "development_min_dcf")
        self.assertIn("false_accept_rate", payload["evaluation"]["rates_at_selected_threshold"])
        self.assertEqual(
            payload["evaluation"]["confidence_intervals_at_selected_threshold"][
                "false_accept_rate"
            ]["method"],
            "wilson_score",
        )

    def test_rejects_unknown_manifest_fields(self) -> None:
        payload = {
            "schema_version": "voiceid-scored-trials/v1",
            "dataset": {"id": "test", "version": "1"},
            "system": {"model_id": "fake", "pipeline_id": "fake"},
            "trials": [],
            "unexpected": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ManifestFormatError, "unknown: unexpected"):
                load_scored_trial_manifest(path)


if __name__ == "__main__":
    unittest.main()
