"""Immutable domain values used by enrollment and verification."""

from __future__ import annotations

import math
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

    def __post_init__(self) -> None:
        values = (
            self.speech_seconds,
            self.speech_ratio,
            self.clipping_ratio,
            self.estimated_snr_db,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("quality metrics must be finite")
        if self.speech_seconds < 0:
            raise ValueError("speech_seconds cannot be negative")
        if not 0.0 <= self.speech_ratio <= 1.0:
            raise ValueError("speech_ratio must be between 0 and 1")
        if not 0.0 <= self.clipping_ratio <= 1.0:
            raise ValueError("clipping_ratio must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class VerificationPolicy:
    policy_id: str = "provisional-cosine-v1"
    speaker_threshold: float = 0.72
    review_margin: float = 0.05
    max_spoof_probability: float = 0.35
    require_spoof_check: bool = False
    min_speech_seconds: float = 2.0
    min_speech_ratio: float = 0.35
    max_clipping_ratio: float = 0.02
    min_snr_db: float = 8.0

    def __post_init__(self) -> None:
        if not self.policy_id:
            raise ValueError("policy_id is required")
        if not -1.0 <= self.speaker_threshold <= 1.0:
            raise ValueError("speaker_threshold must be between -1 and 1")
        if not 0.0 <= self.review_margin <= 2.0:
            raise ValueError("review_margin must be between 0 and 2")
        if not 0.0 <= self.max_spoof_probability <= 1.0:
            raise ValueError("max_spoof_probability must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class VerificationResult:
    decision: Decision
    speaker_score: float | None
    spoof_probability: float | None
    reasons: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return self.decision is Decision.ACCEPT
