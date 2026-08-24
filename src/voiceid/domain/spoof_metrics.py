"""Countermeasure metrics with high scores interpreted as spoof probability."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CountermeasureRates:
    threshold: float
    bonafide_reject_rate: float
    spoof_accept_rate: float
    bonafide_rejects: int
    spoof_accepts: int
    bonafide_trials: int
    spoof_trials: int

    @property
    def balanced_error_rate(self) -> float:
        return (self.bonafide_reject_rate + self.spoof_accept_rate) / 2.0


@dataclass(frozen=True, slots=True)
class CountermeasureCostModel:
    spoof_prior: float = 0.5
    bonafide_reject_cost: float = 1.0
    spoof_accept_cost: float = 1.0

    def __post_init__(self) -> None:
        values = (self.spoof_prior, self.bonafide_reject_cost, self.spoof_accept_cost)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("countermeasure cost values must be finite")
        if not 0.0 < self.spoof_prior < 1.0:
            raise ValueError("spoof_prior must be between 0 and 1")
        if self.bonafide_reject_cost <= 0 or self.spoof_accept_cost <= 0:
            raise ValueError("countermeasure costs must be positive")


@dataclass(frozen=True, slots=True)
class CountermeasureCostMetrics:
    rates: CountermeasureRates
    cost: float
    normalized_cost: float


def countermeasure_rates(
    bonafide_scores: Sequence[float],
    spoof_scores: Sequence[float],
    threshold: float,
) -> CountermeasureRates:
    """Classify scores greater than or equal to threshold as spoof."""
    bonafide = _validate_probabilities(bonafide_scores, "bonafide")
    spoof = _validate_probabilities(spoof_scores, "spoof")
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("countermeasure threshold must be between 0 and 1")
    bonafide_rejects = sum(score >= threshold for score in bonafide)
    spoof_accepts = sum(score < threshold for score in spoof)
    return CountermeasureRates(
        threshold=threshold,
        bonafide_reject_rate=bonafide_rejects / len(bonafide),
        spoof_accept_rate=spoof_accepts / len(spoof),
        bonafide_rejects=bonafide_rejects,
        spoof_accepts=spoof_accepts,
        bonafide_trials=len(bonafide),
        spoof_trials=len(spoof),
    )


def estimate_countermeasure_eer(
    bonafide_scores: Sequence[float], spoof_scores: Sequence[float]
) -> CountermeasureRates:
    bonafide = _validate_probabilities(bonafide_scores, "bonafide")
    spoof = _validate_probabilities(spoof_scores, "spoof")
    evaluated = _threshold_sweep(bonafide, spoof)
    return min(
        evaluated,
        key=lambda item: (
            abs(item.bonafide_reject_rate - item.spoof_accept_rate),
            item.balanced_error_rate,
            item.spoof_accept_rate,
            item.threshold,
        ),
    )


def countermeasure_cost(
    rates: CountermeasureRates,
    model: CountermeasureCostModel | None = None,
) -> CountermeasureCostMetrics:
    model = model or CountermeasureCostModel()
    bonafide_prior = 1.0 - model.spoof_prior
    cost = (
        model.bonafide_reject_cost * bonafide_prior * rates.bonafide_reject_rate
        + model.spoof_accept_cost * model.spoof_prior * rates.spoof_accept_rate
    )
    default_cost = min(
        model.bonafide_reject_cost * bonafide_prior,
        model.spoof_accept_cost * model.spoof_prior,
    )
    return CountermeasureCostMetrics(rates, cost, cost / default_cost)


def minimum_countermeasure_cost(
    bonafide_scores: Sequence[float],
    spoof_scores: Sequence[float],
    model: CountermeasureCostModel | None = None,
) -> CountermeasureCostMetrics:
    bonafide = _validate_probabilities(bonafide_scores, "bonafide")
    spoof = _validate_probabilities(spoof_scores, "spoof")
    cost_model = model or CountermeasureCostModel()
    evaluated = [
        countermeasure_cost(rates, cost_model) for rates in _threshold_sweep(bonafide, spoof)
    ]
    return min(
        evaluated,
        key=lambda item: (
            item.normalized_cost,
            item.rates.spoof_accept_rate,
            item.rates.bonafide_reject_rate,
            item.rates.threshold,
        ),
    )


def _validate_probabilities(values: Sequence[float], label: str) -> tuple[float, ...]:
    scores = tuple(values)
    if not scores:
        raise ValueError(f"{label} countermeasure scores are required")
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in scores):
        raise ValueError(f"{label} countermeasure scores must be numeric")
    normalized = tuple(float(value) for value in scores)
    if any(not math.isfinite(value) for value in normalized):
        raise ValueError(f"{label} countermeasure scores must be finite")
    if any(not 0.0 <= value <= 1.0 for value in normalized):
        raise ValueError(f"{label} countermeasure scores must be between 0 and 1")
    return normalized


def _candidate_thresholds(
    bonafide_scores: Sequence[float], spoof_scores: Sequence[float]
) -> tuple[float, ...]:
    return tuple(sorted({0.0, 1.0, *bonafide_scores, *spoof_scores}))


def _threshold_sweep(
    bonafide_scores: tuple[float, ...], spoof_scores: tuple[float, ...]
) -> tuple[CountermeasureRates, ...]:
    """Evaluate every observed threshold in one ordered pass.

    Scores equal to the threshold remain classified as spoof. Advancing each
    cursor only past strictly smaller scores therefore preserves the public
    ``score >= threshold`` decision contract without an O(n²) rescan.
    """

    bonafide = sorted(bonafide_scores)
    spoof = sorted(spoof_scores)
    bonafide_below = 0
    spoof_below = 0
    evaluated = []
    for threshold in _candidate_thresholds(bonafide, spoof):
        while bonafide_below < len(bonafide) and bonafide[bonafide_below] < threshold:
            bonafide_below += 1
        while spoof_below < len(spoof) and spoof[spoof_below] < threshold:
            spoof_below += 1
        bonafide_rejects = len(bonafide) - bonafide_below
        spoof_accepts = spoof_below
        evaluated.append(
            CountermeasureRates(
                threshold=threshold,
                bonafide_reject_rate=bonafide_rejects / len(bonafide),
                spoof_accept_rate=spoof_accepts / len(spoof),
                bonafide_rejects=bonafide_rejects,
                spoof_accepts=spoof_accepts,
                bonafide_trials=len(bonafide),
                spoof_trials=len(spoof),
            )
        )
    return tuple(evaluated)
