"""Defensive decoder for uncompressed PCM WAVE input."""

from __future__ import annotations

import io
import struct
import wave

from voiceid.domain.audio import AudioBuffer


class WaveDecodingError(ValueError):
    pass


class PcmWaveDecoder:
    def __init__(self, *, max_bytes: int = 10_000_000, max_duration_seconds: float = 30.0) -> None:
        if max_bytes <= 0 or max_duration_seconds <= 0:
            raise ValueError("decoder limits must be positive")
        self._max_bytes = max_bytes
        self._max_duration_seconds = max_duration_seconds

    def decode(self, payload: bytes) -> AudioBuffer:
        if not payload:
            raise WaveDecodingError("audio payload is empty")
        if len(payload) > self._max_bytes:
            raise WaveDecodingError("audio payload exceeds the size limit")

        try:
            with wave.open(io.BytesIO(payload), "rb") as source:
                channels = source.getnchannels()
                sample_width = source.getsampwidth()
                sample_rate = source.getframerate()
                frame_count = source.getnframes()
                compression = source.getcomptype()
                if compression != "NONE":
                    raise WaveDecodingError("compressed WAVE input is not supported")
                if channels not in (1, 2):
                    raise WaveDecodingError("only mono and stereo audio are supported")
                if sample_width != 2:
                    raise WaveDecodingError("only signed 16-bit PCM is supported")
                if sample_rate <= 0 or frame_count / sample_rate > self._max_duration_seconds:
                    raise WaveDecodingError("audio duration exceeds the limit")
                raw = source.readframes(frame_count)
        except (EOFError, wave.Error) as error:
            raise WaveDecodingError("invalid WAVE payload") from error

        try:
            values = struct.unpack(f"<{frame_count * channels}h", raw)
        except struct.error as error:
            raise WaveDecodingError("truncated WAVE payload") from error
        if channels == 1:
            mono = values
        else:
            mono = tuple(
                (values[index] + values[index + 1]) / 2 for index in range(0, len(values), 2)
            )
        return AudioBuffer(tuple(float(value) / 32768.0 for value in mono), sample_rate)
