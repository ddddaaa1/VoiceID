"""Domain values and policy for speaker enrollment."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from .scoring import Vector


@dataclass(frozen=True, slots=True)
class EnrollmentPolicy:
    min_samples: int = 3
    max_samples: int = 8
    outlier_threshold: float = 0.45
    min_speech_seconds: float = 2.0
    min_speech_ratio: float = 0.35
    max_clipping_ratio: float = 0.02
    min_snr_db: float = 8.0

    def __post_init__(self) -> None:
        if self.min_samples < 2 or self.max_samples < self.min_samples:
            raise ValueError("enrollment sample limits are invalid")
        if not -1.0 <= self.outlier_threshold <= 1.0:
            raise ValueError("outlier_threshold must be between -1 and 1")
        if self.min_speech_seconds <= 0 or not 0.0 <= self.min_speech_ratio <= 1.0:
            raise ValueError("enrollment speech requirements are invalid")
        if not 0.0 <= self.max_clipping_ratio <= 1.0:
            raise ValueError("max_clipping_ratio must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class VoiceTemplate:
    template_id: str
    identity_id: str
    embedding: Vector
    model_id: str
    pipeline_id: str
    version: int
    sample_count: int
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.template_id or not self.identity_id:
            raise ValueError("template and identity identifiers are required")
        if not self.model_id or not self.pipeline_id:
            raise ValueError("model and pipeline identifiers are required")
        if self.version <= 0 or self.sample_count <= 0:
            raise ValueError("template version and sample count must be positive")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        norm = math.sqrt(sum(value * value for value in self.embedding))
        if not self.embedding or not math.isclose(norm, 1.0, abs_tol=1e-6):
            raise ValueError("voice template embedding must be L2-normalized")
