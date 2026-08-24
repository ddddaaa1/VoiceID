"""Ports implemented by concrete machine-learning model adapters."""

from __future__ import annotations

from typing import Protocol

from voiceid.domain.audio import AudioBuffer, PreprocessedAudio
from voiceid.domain.scoring import Vector


class ModelInferenceError(RuntimeError):
    """Framework-independent model inference failure."""


class SpeakerEmbedder(Protocol):
    @property
    def model_id(self) -> str: ...

    def embed(self, audio: PreprocessedAudio) -> Vector:
        """Produce a normalized speaker embedding."""


class SpoofDetector(Protocol):
    @property
    def model_id(self) -> str: ...

    def spoof_probability(self, audio: AudioBuffer) -> float:
        """Estimate spoof probability from non-normalized mono 16 kHz waveform."""
