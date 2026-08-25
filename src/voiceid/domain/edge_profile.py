"""Versioned product budgets and evidence evaluation for edge inference."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class EdgeProfileError(ValueError):
    """Raised when an edge profile is incomplete or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class EdgeBudgets:
    artifact_size_mib: float
    model_core_p95_ms: float
    end_to_end_p95_ms: float
    peak_working_set_mib: float
    energy_joules_per_verification: float


@dataclass(frozen=True, slots=True)
class FidelityBudgets:
    minimum_embedding_cosine: float
    p95_absolute_score_delta: float
    maximum_eer_increase_points: float


@dataclass(frozen=True, slots=True)
class EdgeProfile:
    profile_id: str
    source_model_id: str
    target_class: str
    sample_rate: int
    window_seconds: float
    budgets: EdgeBudgets
    fidelity: FidelityBudgets


def load_edge_profile(path: Path) -> EdgeProfile:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EdgeProfileError("edge profile is unavailable or invalid") from error
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "profile_id",
        "source_model_id",
        "target",
        "input",
        "budgets",
        "fidelity",
        "measurement_policy",
    }:
        raise EdgeProfileError("edge profile fields are invalid")
    if payload["schema_version"] != "voiceid-edge-profile/v1":
        raise EdgeProfileError("unsupported edge profile schema")
    target = _object(payload["target"], "target", {"class", "runtime", "precision"})
    input_contract = _object(payload["input"], "input", {"sample_rate", "window_seconds"})
    budgets = _object(
        payload["budgets"],
        "budgets",
        {
            "artifact_size_mib",
            "model_core_p95_ms",
            "end_to_end_p95_ms",
            "peak_working_set_mib",
            "energy_joules_per_verification",
        },
    )
    fidelity = _object(
        payload["fidelity"],
        "fidelity",
        {
            "minimum_embedding_cosine",
            "p95_absolute_score_delta",
            "maximum_eer_increase_points",
        },
    )
    measurement = _object(
        payload["measurement_policy"],
        "measurement_policy",
        {"hardware_specific", "simulated_channels_are_proxies", "power_requires_device_tooling"},
    )
    if target["runtime"] != "onnxruntime" or target["precision"] != "int8-qdq":
        raise EdgeProfileError("edge target runtime or precision is unsupported")
    if (
        measurement["hardware_specific"] is not True
        or measurement["simulated_channels_are_proxies"] is not True
        or measurement["power_requires_device_tooling"] is not True
    ):
        raise EdgeProfileError("edge measurement policy must preserve evidence boundaries")

    minimum_cosine = _number(fidelity["minimum_embedding_cosine"], "minimum cosine")
    if not 0.0 < minimum_cosine <= 1.0:
        raise EdgeProfileError("minimum embedding cosine must be in (0, 1]")
    score_delta = _number(fidelity["p95_absolute_score_delta"], "score delta")
    eer_delta = _number(fidelity["maximum_eer_increase_points"], "EER increase")
    if score_delta <= 0.0 or eer_delta <= 0.0:
        raise EdgeProfileError("fidelity degradation budgets must be positive")

    return EdgeProfile(
        profile_id=_string(payload["profile_id"], "profile_id"),
        source_model_id=_string(payload["source_model_id"], "source_model_id"),
        target_class=_string(target["class"], "target.class"),
        sample_rate=_positive_int(input_contract["sample_rate"], "input.sample_rate"),
        window_seconds=_positive_number(input_contract["window_seconds"], "window_seconds"),
        budgets=EdgeBudgets(
            artifact_size_mib=_positive_number(budgets["artifact_size_mib"], "artifact size"),
            model_core_p95_ms=_positive_number(budgets["model_core_p95_ms"], "core latency"),
            end_to_end_p95_ms=_positive_number(budgets["end_to_end_p95_ms"], "end-to-end latency"),
            peak_working_set_mib=_positive_number(budgets["peak_working_set_mib"], "working set"),
            energy_joules_per_verification=_positive_number(
                budgets["energy_joules_per_verification"], "energy"
            ),
        ),
        fidelity=FidelityBudgets(
            minimum_embedding_cosine=minimum_cosine,
            p95_absolute_score_delta=score_delta,
            maximum_eer_increase_points=eer_delta,
        ),
    )


def _object(value: object, location: str, fields: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise EdgeProfileError(f"{location} fields are invalid")
    return value


def _string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise EdgeProfileError(f"{location} must be a non-empty string")
    return value


def _number(value: object, location: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise EdgeProfileError(f"{location} must be numeric")
    return float(value)


def _positive_number(value: object, location: str) -> float:
    number = _number(value, location)
    if number <= 0.0:
        raise EdgeProfileError(f"{location} must be positive")
    return number


def _positive_int(value: object, location: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise EdgeProfileError(f"{location} must be a positive integer")
    return value
