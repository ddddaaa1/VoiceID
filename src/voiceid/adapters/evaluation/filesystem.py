"""Bounded, integrity-checked filesystem audio adapter."""

from __future__ import annotations

import hashlib
from pathlib import Path

from voiceid.domain.evaluation import AudioFileReference
from voiceid.ports.evaluation import AudioAssetUnavailable


class HashedAudioFileReader:
    def __init__(self, base_directory: Path, *, max_file_bytes: int = 10_000_000) -> None:
        if max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be positive")
        self._base_directory = base_directory.resolve()
        self._max_file_bytes = max_file_bytes

    def read(self, reference: AudioFileReference) -> bytes:
        path = (self._base_directory / reference.path).resolve()
        if not path.is_relative_to(self._base_directory):
            raise AudioAssetUnavailable("path_outside_dataset", reference.path)
        try:
            size = path.stat().st_size
        except OSError as error:
            raise AudioAssetUnavailable("file_not_found", reference.path) from error
        if not path.is_file():
            raise AudioAssetUnavailable("file_not_found", reference.path)
        if size <= 0:
            raise AudioAssetUnavailable("empty_file", reference.path)
        if size > self._max_file_bytes:
            raise AudioAssetUnavailable("file_too_large", reference.path)
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise AudioAssetUnavailable("file_unreadable", reference.path) from error
        digest = hashlib.sha256(payload).hexdigest()
        if digest != reference.sha256:
            raise AudioAssetUnavailable("checksum_mismatch", reference.path)
        return payload
