"""Ports for decoding audio and detecting speech boundaries."""

from __future__ import annotations

from typing import Protocol

from voiceid.domain.audio import AudioBuffer, SpeechSegment


class AudioDecoder(Protocol):
    def decode(self, payload: bytes) -> AudioBuffer:
        """Decode an untrusted audio payload into normalized mono PCM."""


class VoiceActivityDetector(Protocol):
    def detect(self, audio: AudioBuffer) -> tuple[SpeechSegment, ...]:
        """Return speech intervals using sample offsets in the provided buffer."""
