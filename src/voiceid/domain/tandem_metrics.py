"""Dependency-free tandem detection cost metrics compatible with ASVspoof 2021."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TandemCoefficients:
    """Fixed-ASV coefficients in ``C0 + C1 * Pmiss_cm + C2 * Pfa_cm``."""

    c0: float
    c1: float
    c2: float

    def __post_init__(self) -> None:
        values = (self.c0, self.c1, self.c2)
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise ValueError("t-DCF coefficients must be finite and non-negative")
        if self.normalizer <= 0.0:
            raise ValueError("t-DCF coefficients require a positive normalizer")

    @property
    def normalizer(self) -> float:
        return self.c0 + min(self.c1, self.c2)


@dataclass(frozen=True, slots=True)
class TandemOperatingPoint:
    threshold: float
    bonafide_reject_rate: float
    spoof_accept_rate: float
    normalized_cost: float


@dataclass(frozen=True, slots=True)
class TandemEvaluation:
    minimum: TandemOperatingPoint
    observed_eer: float
    eer_threshold: float
    coefficients: TandemCoefficients
    bonafide_trials: int
    spoof_trials: int


def evaluate_tandem_cost(
    bonafide_support_scores: Sequence[float],
    spoof_support_scores: Sequence[float],
    coefficients: TandemCoefficients,
) -> TandemEvaluation:
    """Evaluate CM EER and minimum normalized t-DCF for a fixed ASV system.

    Higher input scores must indicate stronger support for bona fide speech. The
    threshold sweep intentionally matches the stable-sort recipe in the official
    ASVspoof 2021 evaluation package.
    """

    bonafide = _validate_scores(bonafide_support_scores, "bonafide")
    spoof = _validate_scores(spoof_support_scores, "spoof")
    curve = _det_curve(bonafide, spoof)
    points = tuple(
        TandemOperatingPoint(
            threshold=threshold,
            bonafide_reject_rate=miss,
            spoof_accept_rate=false_accept,
            normalized_cost=(
                coefficients.c0
                + coefficients.c1 * miss
                + coefficients.c2 * false_accept
            )
            / coefficients.normalizer,
        )
        for miss, false_accept, threshold in curve
    )
    minimum = min(
        points,
        key=lambda point: (
            point.normalized_cost,
            point.spoof_accept_rate,
            point.bonafide_reject_rate,
            point.threshold,
        ),
    )
    eer_point = min(
        curve,
        key=lambda item: abs(item[0] - item[1]),
    )
    return TandemEvaluation(
        minimum=minimum,
        observed_eer=(eer_point[0] + eer_point[1]) / 2.0,
        eer_threshold=eer_point[2],
        coefficients=coefficients,
        bonafide_trials=len(bonafide),
        spoof_trials=len(spoof),
    )


def _det_curve(
    bonafide: tuple[float, ...], spoof: tuple[float, ...]
) -> tuple[tuple[float, float, float], ...]:
    labeled = [(score, 1) for score in bonafide]
    labeled.extend((score, 0) for score in spoof)
    labeled.sort(key=lambda item: item[0])
    target_seen = 0
    spoof_remaining = len(spoof)
    curve = [(0.0, 1.0, labeled[0][0] - 0.001)]
    for score, target_label in labeled:
        target_seen += target_label
        spoof_remaining -= 1 - target_label
        curve.append(
            (
                target_seen / len(bonafide),
                spoof_remaining / len(spoof),
                score,
            )
        )
    return tuple(curve)


def _validate_scores(values: Sequence[float], label: str) -> tuple[float, ...]:
    scores = tuple(values)
    if not scores:
        raise ValueError(f"{label} scores are required")
    if any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        for value in scores
    ):
        raise ValueError(f"{label} scores must be finite numbers")
    return tuple(float(value) for value in scores)
