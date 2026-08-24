"""Energy-based VAD baseline used until the neural VAD adapter is introduced."""

from __future__ import annotations

import math

from voiceid.domain.audio import AudioBuffer, SpeechSegment


class EnergyVoiceActivityDetector:
    def __init__(
        self,
        *,
        frame_ms: int = 30,
        hop_ms: int = 10,
        threshold_dbfs: float = -38.0,
        min_speech_ms: int = 150,
        padding_ms: int = 80,
    ) -> None:
        if frame_ms <= 0 or hop_ms <= 0 or min_speech_ms <= 0 or padding_ms < 0:
            raise ValueError("VAD timing parameters are invalid")
        self._frame_ms = frame_ms
        self._hop_ms = hop_ms
        self._threshold_dbfs = threshold_dbfs
        self._min_speech_ms = min_speech_ms
        self._padding_ms = padding_ms

    def detect(self, audio: AudioBuffer) -> tuple[SpeechSegment, ...]:
        frame_size = max(1, round(audio.sample_rate * self._frame_ms / 1000))
        hop_size = max(1, round(audio.sample_rate * self._hop_ms / 1000))
        active: list[tuple[int, int]] = []

        for start in range(0, len(audio.samples), hop_size):
            end = min(start + frame_size, len(audio.samples))
            frame = audio.samples[start:end]
            rms = math.sqrt(sum(sample * sample for sample in frame) / len(frame))
            dbfs = 20.0 * math.log10(max(rms, 1e-12))
            if dbfs >= self._threshold_dbfs:
                active.append((start, end))

        if not active:
            return ()

        padding = round(audio.sample_rate * self._padding_ms / 1000)
        merged: list[list[int]] = []
        for start, end in active:
            start = max(0, start - padding)
            end = min(len(audio.samples), end + padding)
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])

        minimum = round(audio.sample_rate * self._min_speech_ms / 1000)
        return tuple(
            SpeechSegment(start, end) for start, end in merged if end - start >= minimum
        )
