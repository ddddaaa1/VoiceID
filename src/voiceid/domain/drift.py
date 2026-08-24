"""Distribution drift metrics for privacy-preserving score monitoring."""

from __future__ import annotations

import bisect
import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class DriftStatus(StrEnum):
    STABLE = "stable"
    WARNING = "warning"
    ALERT = "alert"


@dataclass(frozen=True, slots=True)
class DriftBaseline:
    model_id: str
    bin_edges: tuple[float, ...]
    expected_proportions: tuple[float, ...]
    sample_count: int

    def __post_init__(self) -> None:
        if not self.model_id or self.sample_count <= 0:
            raise ValueError("drift baseline identity and sample count are required")
        if any(not math.isfinite(edge) for edge in self.bin_edges):
            raise ValueError("drift baseline edges must be finite")
        if tuple(sorted(set(self.bin_edges))) != self.bin_edges:
            raise ValueError("drift baseline edges must be strictly increasing")
        if len(self.expected_proportions) != len(self.bin_edges) + 1:
            raise ValueError("drift proportions must define every histogram bin")
        if any(not math.isfinite(value) or value < 0.0 for value in self.expected_proportions):
            raise ValueError("drift proportions must be finite and non-negative")
        if not math.isclose(sum(self.expected_proportions), 1.0, abs_tol=1e-9):
            raise ValueError("drift proportions must sum to one")


@dataclass(frozen=True, slots=True)
class DriftReport:
    model_id: str
    baseline_samples: int
    current_samples: int
    population_stability_index: float
    status: DriftStatus
    current_proportions: tuple[float, ...]


def evaluate_score_drift(
    baseline: DriftBaseline,
    current_scores: Sequence[float],
    *,
    warning_threshold: float = 0.1,
    alert_threshold: float = 0.25,
    minimum_samples: int = 30,
) -> DriftReport:
    if not 0.0 < warning_threshold < alert_threshold:
        raise ValueError("drift thresholds must be positive and ordered")
    if minimum_samples <= 0:
        raise ValueError("minimum drift sample count must be positive")
    scores = tuple(float(score) for score in current_scores)
    if len(scores) < minimum_samples:
        raise ValueError("insufficient current scores for drift evaluation")
    if any(not math.isfinite(score) for score in scores):
        raise ValueError("drift scores must be finite")

    counts = [0] * (len(baseline.bin_edges) + 1)
    for score in scores:
        counts[bisect.bisect_right(baseline.bin_edges, score)] += 1
    current = tuple(count / len(scores) for count in counts)
    epsilon = 1e-6
    psi = sum(
        (actual - expected) * math.log((actual + epsilon) / (expected + epsilon))
        for expected, actual in zip(baseline.expected_proportions, current, strict=True)
    )
    if psi >= alert_threshold:
        status = DriftStatus.ALERT
    elif psi >= warning_threshold:
        status = DriftStatus.WARNING
    else:
        status = DriftStatus.STABLE
    return DriftReport(
        model_id=baseline.model_id,
        baseline_samples=baseline.sample_count,
        current_samples=len(scores),
        population_stability_index=psi,
        status=status,
        current_proportions=current,
    )
