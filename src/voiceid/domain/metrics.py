"""Threshold metrics for reproducible speaker-verification evaluation."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThresholdMetrics:
    threshold: float
    false_accept_rate: float
    false_reject_rate: float
    false_accepts: int
    false_rejects: int
    genuine_trials: int
    impostor_trials: int

    @property
    def balanced_error_rate(self) -> float:
        return (self.false_accept_rate + self.false_reject_rate) / 2


@dataclass(frozen=True, slots=True)
class DetectionCostModel:
    target_probability: float = 0.01
    false_accept_cost: float = 1.0
    false_reject_cost: float = 1.0

    def __post_init__(self) -> None:
        values = (
            self.target_probability,
            self.false_accept_cost,
            self.false_reject_cost,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("detection cost values must be finite")
        if not 0.0 < self.target_probability < 1.0:
            raise ValueError("target_probability must be between 0 and 1")
        if self.false_accept_cost <= 0 or self.false_reject_cost <= 0:
            raise ValueError("detection costs must be positive")


@dataclass(frozen=True, slots=True)
class DetectionCostMetrics:
    rates: ThresholdMetrics
    cost: float
    normalized_cost: float


def rates_at_threshold(
    genuine_scores: Sequence[float], impostor_scores: Sequence[float], threshold: float
) -> ThresholdMetrics:
    genuine = _validate_scores(genuine_scores, "genuine")
    impostor = _validate_scores(impostor_scores, "impostor")
    if not math.isfinite(threshold):
        raise ValueError("threshold must be finite")
    false_rejects = sum(score < threshold for score in genuine)
    false_accepts = sum(score >= threshold for score in impostor)
    return ThresholdMetrics(
        threshold=threshold,
        false_accept_rate=false_accepts / len(impostor),
        false_reject_rate=false_rejects / len(genuine),
        false_accepts=false_accepts,
        false_rejects=false_rejects,
        genuine_trials=len(genuine),
        impostor_trials=len(impostor),
    )


def estimate_eer(
    genuine_scores: Sequence[float], impostor_scores: Sequence[float]
) -> ThresholdMetrics:
    """Find the observed threshold with the smallest FAR/FRR gap."""
    genuine = _validate_scores(genuine_scores, "genuine")
    impostor = _validate_scores(impostor_scores, "impostor")
    evaluated = [
        rates_at_threshold(genuine, impostor, threshold)
        for threshold in _candidate_thresholds(genuine, impostor)
    ]
    return min(
        evaluated,
        key=lambda item: (
            abs(item.false_accept_rate - item.false_reject_rate),
            item.balanced_error_rate,
            -item.threshold,
        ),
    )


def detection_cost(
    rates: ThresholdMetrics,
    model: DetectionCostModel | None = None,
) -> DetectionCostMetrics:
    model = model or DetectionCostModel()
    miss_component = (
        model.false_reject_cost * model.target_probability * rates.false_reject_rate
    )
    false_alarm_component = (
        model.false_accept_cost * (1 - model.target_probability) * rates.false_accept_rate
    )
    cost = miss_component + false_alarm_component
    default_cost = min(
        model.false_reject_cost * model.target_probability,
        model.false_accept_cost * (1 - model.target_probability),
    )
    return DetectionCostMetrics(rates, cost, cost / default_cost)


def minimum_detection_cost(
    genuine_scores: Sequence[float],
    impostor_scores: Sequence[float],
    model: DetectionCostModel | None = None,
) -> DetectionCostMetrics:
    """Select a threshold that minimizes normalized detection cost."""
    genuine = _validate_scores(genuine_scores, "genuine")
    impostor = _validate_scores(impostor_scores, "impostor")
    cost_model = model or DetectionCostModel()
    evaluated = [
        detection_cost(rates_at_threshold(genuine, impostor, threshold), cost_model)
        for threshold in _candidate_thresholds(genuine, impostor)
    ]
    return min(
        evaluated,
        key=lambda item: (
            item.normalized_cost,
            item.rates.false_accept_rate,
            -item.rates.threshold,
        ),
    )


def _validate_scores(scores: Sequence[float], label: str) -> tuple[float, ...]:
    values = tuple(scores)
    if not values:
        raise ValueError(f"{label} scores are required")
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in values):
        raise ValueError(f"{label} scores must be numeric")
    normalized = tuple(float(value) for value in values)
    if any(not math.isfinite(value) for value in normalized):
        raise ValueError(f"{label} scores must be finite")
    if any(not -1.0 <= value <= 1.0 for value in normalized):
        raise ValueError(f"{label} scores must be between -1 and 1")
    return normalized


def _candidate_thresholds(
    genuine_scores: Sequence[float], impostor_scores: Sequence[float]
) -> tuple[float, ...]:
    observed = sorted(set(genuine_scores) | set(impostor_scores))
    return (
        math.nextafter(observed[0], -math.inf),
        *observed,
        math.nextafter(observed[-1], math.inf),
    )
