"""Strict JSON adapter for versioned scored-trial manifests and reports."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from voiceid.application.evaluation import EvaluationReport
from voiceid.domain.evaluation import (
    EvaluationProtocolError,
    ScoredTrial,
    ScoredTrialManifest,
    TrialLabel,
    TrialPartition,
)


class ManifestFormatError(ValueError):
    """Raised when JSON does not match the scored-trial manifest contract."""


def load_scored_trial_manifest(path: Path) -> ScoredTrialManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ManifestFormatError(f"could not read manifest: {path}") from error
    except json.JSONDecodeError as error:
        raise ManifestFormatError(f"manifest is not valid JSON: {error.msg}") from error

    root = _object(payload, "manifest")
    _exact_keys(root, {"schema_version", "dataset", "system", "trials"}, "manifest")
    dataset = _object(root["dataset"], "dataset")
    system = _object(root["system"], "system")
    _exact_keys(dataset, {"id", "version"}, "dataset")
    _exact_keys(system, {"model_id", "pipeline_id"}, "system")
    if not isinstance(root["trials"], list):
        raise ManifestFormatError("trials must be an array")

    trials = tuple(
        _parse_trial(value, index) for index, value in enumerate(root["trials"])
    )
    try:
        return ScoredTrialManifest(
            schema_version=_string(root["schema_version"], "schema_version"),
            dataset_id=_string(dataset["id"], "dataset.id"),
            dataset_version=_string(dataset["version"], "dataset.version"),
            model_id=_string(system["model_id"], "system.model_id"),
            pipeline_id=_string(system["pipeline_id"], "system.pipeline_id"),
            trials=trials,
        )
    except EvaluationProtocolError as error:
        raise ManifestFormatError(str(error)) from error


def evaluation_report_payload(report: EvaluationReport) -> dict[str, Any]:
    return {
        "schema_version": report.schema_version,
        "dataset": {"id": report.dataset_id, "version": report.dataset_version},
        "system": {"model_id": report.model_id, "pipeline_id": report.pipeline_id},
        "calibration": {
            "threshold_source": report.threshold_source,
            "selected_threshold": report.selected_threshold,
            "cost_model": asdict(report.cost_model),
        },
        "development": _partition_payload(report.development),
        "evaluation": _partition_payload(report.evaluation),
        "evaluation_conditions": [
            {
                "condition": condition.condition,
                "genuine_trials": condition.genuine_trials,
                "impostor_trials": condition.impostor_trials,
                "rates_at_selected_threshold": (
                    _rates_payload(condition.rates_at_selected_threshold)
                    if condition.rates_at_selected_threshold
                    else None
                ),
                "confidence_intervals_at_selected_threshold": (
                    {
                        "false_accept_rate": _interval_payload(
                            condition.false_accept_interval
                        ),
                        "false_reject_rate": _interval_payload(
                            condition.false_reject_interval
                        ),
                    }
                    if condition.false_accept_interval
                    and condition.false_reject_interval
                    else None
                ),
            }
            for condition in report.evaluation_conditions
        ],
    }


def scored_trial_manifest_payload(manifest: ScoredTrialManifest) -> dict[str, Any]:
    return {
        "schema_version": manifest.schema_version,
        "dataset": {"id": manifest.dataset_id, "version": manifest.dataset_version},
        "system": {"model_id": manifest.model_id, "pipeline_id": manifest.pipeline_id},
        "trials": [
            {
                "trial_id": trial.trial_id,
                "partition": trial.partition.value,
                "label": trial.label.value,
                "enrollment_speaker_id": trial.enrollment_speaker_id,
                "probe_speaker_id": trial.probe_speaker_id,
                "score": trial.score,
                "condition": trial.condition,
            }
            for trial in manifest.trials
        ],
    }


def write_scored_trial_manifest(manifest: ScoredTrialManifest, path: Path) -> None:
    payload = json.dumps(scored_trial_manifest_payload(manifest), indent=2, sort_keys=True)
    path.write_text(f"{payload}\n", encoding="utf-8")


def write_evaluation_report(report: EvaluationReport, path: Path) -> None:
    payload = json.dumps(evaluation_report_payload(report), indent=2, sort_keys=True)
    path.write_text(f"{payload}\n", encoding="utf-8")


def _parse_trial(value: object, index: int) -> ScoredTrial:
    location = f"trials[{index}]"
    trial = _object(value, location)
    expected = {
        "trial_id",
        "partition",
        "label",
        "enrollment_speaker_id",
        "probe_speaker_id",
        "score",
        "condition",
    }
    _exact_keys(trial, expected, location)
    score = trial["score"]
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise ManifestFormatError(f"{location}.score must be numeric")
    try:
        return ScoredTrial(
            trial_id=_string(trial["trial_id"], f"{location}.trial_id"),
            partition=TrialPartition(
                _string(trial["partition"], f"{location}.partition")
            ),
            label=TrialLabel(_string(trial["label"], f"{location}.label")),
            enrollment_speaker_id=_string(
                trial["enrollment_speaker_id"], f"{location}.enrollment_speaker_id"
            ),
            probe_speaker_id=_string(
                trial["probe_speaker_id"], f"{location}.probe_speaker_id"
            ),
            score=float(score),
            condition=_string(trial["condition"], f"{location}.condition"),
        )
    except (EvaluationProtocolError, ValueError) as error:
        raise ManifestFormatError(f"{location}: {error}") from error


def _partition_payload(partition: Any) -> dict[str, Any]:
    return {
        "genuine_trials": partition.genuine_trials,
        "impostor_trials": partition.impostor_trials,
        "rates_at_selected_threshold": _rates_payload(
            partition.rates_at_selected_threshold
        ),
        "observed_eer": {
            **_rates_payload(partition.observed_eer),
            "estimated_eer": partition.observed_eer.balanced_error_rate,
        },
        "minimum_dcf": _cost_payload(partition.minimum_dcf),
        "cost_at_selected_threshold": _cost_payload(
            partition.cost_at_selected_threshold
        ),
        "confidence_intervals_at_selected_threshold": {
            "false_accept_rate": _interval_payload(partition.false_accept_interval),
            "false_reject_rate": _interval_payload(partition.false_reject_interval),
        },
    }


def _rates_payload(rates: Any) -> dict[str, Any]:
    return {
        "threshold": rates.threshold,
        "false_accept_rate": rates.false_accept_rate,
        "false_reject_rate": rates.false_reject_rate,
        "false_accepts": rates.false_accepts,
        "false_rejects": rates.false_rejects,
        "genuine_trials": rates.genuine_trials,
        "impostor_trials": rates.impostor_trials,
    }


def _cost_payload(cost: Any) -> dict[str, Any]:
    return {
        "threshold": cost.rates.threshold,
        "cost": cost.cost,
        "normalized_cost": cost.normalized_cost,
        "false_accept_rate": cost.rates.false_accept_rate,
        "false_reject_rate": cost.rates.false_reject_rate,
    }


def _interval_payload(interval: Any) -> dict[str, Any]:
    return {
        "method": interval.method,
        "confidence_level": interval.confidence_level,
        "lower": interval.lower,
        "upper": interval.upper,
    }


def _object(value: object, location: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ManifestFormatError(f"{location} must be an object")
    return value


def _string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise ManifestFormatError(f"{location} must be a non-empty string")
    return value


def _exact_keys(value: dict[str, object], expected: set[str], location: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        parts = []
        if missing:
            parts.append(f"missing: {', '.join(missing)}")
        if unknown:
            parts.append(f"unknown: {', '.join(unknown)}")
        raise ManifestFormatError(f"{location} fields are invalid ({'; '.join(parts)})")
