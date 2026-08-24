"""Strict JSON adapter for anti-spoofing score manifests and reports."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from voiceid.application.spoof_evaluation import SpoofEvaluationReport
from voiceid.domain.evaluation import TrialPartition
from voiceid.domain.spoofing import (
    AttackCategory,
    SpoofLabel,
    SpoofProtocolError,
    SpoofScoreManifest,
    SpoofScoreTrial,
)

from .json_manifest import ManifestFormatError


def load_spoof_score_manifest(path: Path) -> SpoofScoreManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ManifestFormatError(f"could not read spoof manifest: {path}") from error
    except json.JSONDecodeError as error:
        raise ManifestFormatError(
            f"spoof manifest is not valid JSON: {error.msg}"
        ) from error

    root = _object(payload, "manifest")
    _exact_keys(root, {"schema_version", "dataset", "system", "trials"}, "manifest")
    dataset = _object(root["dataset"], "dataset")
    system = _object(root["system"], "system")
    _exact_keys(dataset, {"id", "version"}, "dataset")
    _exact_keys(system, {"countermeasure_model_id", "pipeline_id"}, "system")
    trials = _array(root["trials"], "trials")
    try:
        return SpoofScoreManifest(
            schema_version=_string(root["schema_version"], "schema_version"),
            dataset_id=_string(dataset["id"], "dataset.id"),
            dataset_version=_string(dataset["version"], "dataset.version"),
            countermeasure_model_id=_string(
                system["countermeasure_model_id"], "system.countermeasure_model_id"
            ),
            pipeline_id=_string(system["pipeline_id"], "system.pipeline_id"),
            trials=tuple(_parse_trial(value, index) for index, value in enumerate(trials)),
        )
    except (SpoofProtocolError, ValueError) as error:
        raise ManifestFormatError(str(error)) from error


def spoof_evaluation_report_payload(report: SpoofEvaluationReport) -> dict[str, Any]:
    return {
        "schema_version": report.schema_version,
        "dataset": {"id": report.dataset_id, "version": report.dataset_version},
        "system": {
            "countermeasure_model_id": report.countermeasure_model_id,
            "pipeline_id": report.pipeline_id,
        },
        "calibration": {
            "threshold_source": report.threshold_source,
            "selected_threshold": report.selected_threshold,
            "score_semantics": "higher_is_more_likely_spoof",
            "cost_model": asdict(report.cost_model),
        },
        "development": _partition_payload(report.development),
        "evaluation": _partition_payload(report.evaluation),
        "evaluation_attacks": [
            {
                "attack_category": attack.attack_category.value,
                "attack_ids": list(attack.attack_ids),
                "spoof_trials": attack.spoof_trials,
                "spoof_accepts": attack.spoof_accepts,
                "spoof_accept_rate": attack.spoof_accept_rate,
                "spoof_accept_interval": _interval_payload(
                    attack.spoof_accept_interval
                ),
            }
            for attack in report.evaluation_attacks
        ],
    }


def write_spoof_evaluation_report(report: SpoofEvaluationReport, path: Path) -> None:
    payload = json.dumps(
        spoof_evaluation_report_payload(report), indent=2, sort_keys=True
    )
    path.write_text(f"{payload}\n", encoding="utf-8")


def _parse_trial(value: object, index: int) -> SpoofScoreTrial:
    location = f"trials[{index}]"
    trial = _object(value, location)
    _exact_keys(
        trial,
        {
            "trial_id",
            "partition",
            "speaker_id",
            "label",
            "attack_category",
            "attack_id",
            "spoof_probability",
            "condition",
        },
        location,
    )
    probability = trial["spoof_probability"]
    if not isinstance(probability, (int, float)) or isinstance(probability, bool):
        raise ManifestFormatError(f"{location}.spoof_probability must be numeric")
    try:
        return SpoofScoreTrial(
            trial_id=_string(trial["trial_id"], f"{location}.trial_id"),
            partition=TrialPartition(
                _string(trial["partition"], f"{location}.partition")
            ),
            speaker_id=_string(trial["speaker_id"], f"{location}.speaker_id"),
            label=SpoofLabel(_string(trial["label"], f"{location}.label")),
            attack_category=AttackCategory(
                _string(trial["attack_category"], f"{location}.attack_category")
            ),
            attack_id=_string(trial["attack_id"], f"{location}.attack_id"),
            spoof_probability=float(probability),
            condition=_string(trial["condition"], f"{location}.condition"),
        )
    except (SpoofProtocolError, ValueError) as error:
        raise ManifestFormatError(f"{location}: {error}") from error


def _partition_payload(partition: Any) -> dict[str, Any]:
    return {
        "bonafide_trials": partition.bonafide_trials,
        "spoof_trials": partition.spoof_trials,
        "rates_at_selected_threshold": _rates_payload(
            partition.rates_at_selected_threshold
        ),
        "confidence_intervals_at_selected_threshold": {
            "bonafide_reject_rate": _interval_payload(
                partition.bonafide_reject_interval
            ),
            "spoof_accept_rate": _interval_payload(partition.spoof_accept_interval),
        },
        "observed_countermeasure_eer": {
            **_rates_payload(partition.observed_eer),
            "estimated_eer": partition.observed_eer.balanced_error_rate,
        },
        "minimum_countermeasure_cost": _cost_payload(partition.minimum_cost),
        "cost_at_selected_threshold": _cost_payload(
            partition.cost_at_selected_threshold
        ),
    }


def _rates_payload(rates: Any) -> dict[str, Any]:
    return {
        "threshold": rates.threshold,
        "bonafide_reject_rate": rates.bonafide_reject_rate,
        "spoof_accept_rate": rates.spoof_accept_rate,
        "bonafide_rejects": rates.bonafide_rejects,
        "spoof_accepts": rates.spoof_accepts,
        "bonafide_trials": rates.bonafide_trials,
        "spoof_trials": rates.spoof_trials,
    }


def _cost_payload(cost: Any) -> dict[str, Any]:
    return {
        "threshold": cost.rates.threshold,
        "cost": cost.cost,
        "normalized_cost": cost.normalized_cost,
        "bonafide_reject_rate": cost.rates.bonafide_reject_rate,
        "spoof_accept_rate": cost.rates.spoof_accept_rate,
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


def _array(value: object, location: str) -> list[object]:
    if not isinstance(value, list):
        raise ManifestFormatError(f"{location} must be an array")
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
