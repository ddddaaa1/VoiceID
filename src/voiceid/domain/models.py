"""Immutable domain values used by enrollment and verification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Decision(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class QualityReport:
    speech_seconds: float
    speech_ratio: float
    clipping_ratio: float
    estimated_snr_db: float


@dataclass(frozen=True, slots=True)
class VerificationPolicy:
    speaker_threshold: float = 0.72
    review_margin: float = 0.05
    max_spoof_probability: float = 0.35
    min_speech_seconds: float = 2.0
    min_speech_ratio: float = 0.35
    max_clipping_ratio: float = 0.02
    min_snr_db: float = 8.0


@dataclass(frozen=True, slots=True)
class VerificationResult:
    decision: Decision
    speaker_score: float
    spoof_probability: float
    reasons: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return self.decision is Decision.ACCEPT
