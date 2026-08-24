"""Ports used by the evaluation scoring workflow."""

from __future__ import annotations

from typing import Protocol

from voiceid.domain.evaluation import AudioFileReference


class AudioAssetUnavailable(ValueError):
    def __init__(self, code: str, path: str) -> None:
        super().__init__(code)
        self.code = code
        self.path = path


class AudioAssetReader(Protocol):
    def read(self, reference: AudioFileReference) -> bytes: ...
