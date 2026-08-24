"""Audio values shared across preprocessing and model adapters."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AudioBuffer:
    """Normalized mono PCM samples in the closed interval [-1, 1]."""

    samples: tuple[float, ...]
    sample_rate: int

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if not self.samples:
            raise ValueError("audio must contain at least one sample")
        if any(not math.isfinite(sample) for sample in self.samples):
            raise ValueError("audio samples must be finite")
        if any(abs(sample) > 1.0 for sample in self.samples):
            raise ValueError("audio samples must be normalized to [-1, 1]")

    @property
    def duration_seconds(self) -> float:
        return len(self.samples) / self.sample_rate


@dataclass(frozen=True, slots=True)
class SpeechSegment:
    start_sample: int
    end_sample: int

    def __post_init__(self) -> None:
        if self.start_sample < 0 or self.end_sample <= self.start_sample:
            raise ValueError("a speech segment must have positive duration")


@dataclass(frozen=True, slots=True)
class PreprocessedAudio:
    audio: AudioBuffer
    speech_segments: tuple[SpeechSegment, ...]

    def __post_init__(self) -> None:
        previous_end = 0
        for segment in self.speech_segments:
            if segment.end_sample > len(self.audio.samples):
                raise ValueError("speech segments must stay within the audio buffer")
            if segment.start_sample < previous_end:
                raise ValueError("speech segments must be ordered and non-overlapping")
            previous_end = segment.end_sample
