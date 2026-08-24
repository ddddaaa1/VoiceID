"""Ports implemented by concrete machine-learning model adapters."""

from __future__ import annotations

from typing import Protocol

from voiceid.domain.audio import PreprocessedAudio
from voiceid.domain.scoring import Vector


class SpeakerEmbedder(Protocol):
    @property
    def model_id(self) -> str: ...

    def embed(self, audio: PreprocessedAudio) -> Vector:
        """Produce a normalized speaker embedding."""


class SpoofDetector(Protocol):
    @property
    def model_id(self) -> str: ...

    def spoof_probability(self, audio: PreprocessedAudio) -> float:
        """Estimate the probability that a sample is replayed or synthetic."""
