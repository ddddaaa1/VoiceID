"""Threshold metrics for reproducible speaker-verification evaluation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThresholdMetrics:
    threshold: float
    false_accept_rate: float
    false_reject_rate: float


def rates_at_threshold(
    genuine_scores: Sequence[float], impostor_scores: Sequence[float], threshold: float
) -> ThresholdMetrics:
    if not genuine_scores or not impostor_scores:
        raise ValueError("genuine and impostor scores are required")
    false_rejects = sum(score < threshold for score in genuine_scores)
    false_accepts = sum(score >= threshold for score in impostor_scores)
    return ThresholdMetrics(
        threshold=threshold,
        false_accept_rate=false_accepts / len(impostor_scores),
        false_reject_rate=false_rejects / len(genuine_scores),
    )


def estimate_eer(
    genuine_scores: Sequence[float], impostor_scores: Sequence[float]
) -> ThresholdMetrics:
    """Find the observed threshold with the smallest FAR/FRR gap."""
    candidates = sorted(set(genuine_scores) | set(impostor_scores))
    if not candidates:
        raise ValueError("scores are required")
    evaluated = [rates_at_threshold(genuine_scores, impostor_scores, value) for value in candidates]
    return min(evaluated, key=lambda item: abs(item.false_accept_rate - item.false_reject_rate))
