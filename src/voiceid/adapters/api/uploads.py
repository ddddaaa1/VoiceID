"""Bounded reads for untrusted multipart uploads."""

from __future__ import annotations

from fastapi import UploadFile

from .container import ApiSettings
from .errors import ApiError

CHUNK_BYTES = 1_048_576


async def read_upload(upload: UploadFile, settings: ApiSettings) -> bytes:
    if upload.content_type not in settings.allowed_content_types:
        await upload.close()
        raise ApiError(
            415,
            "unsupported_media_type",
            "Only PCM WAVE uploads are accepted.",
            details={"content_type": upload.content_type},
        )

    payload = bytearray()
    try:
        while chunk := await upload.read(CHUNK_BYTES):
            payload.extend(chunk)
            if len(payload) > settings.max_file_bytes:
                raise ApiError(
                    413,
                    "file_too_large",
                    "An uploaded audio file exceeds the configured size limit.",
                )
    finally:
        await upload.close()

    if not payload:
        raise ApiError(422, "empty_audio_file", "An uploaded audio file is empty.")
    return bytes(payload)


async def read_uploads(uploads: list[UploadFile], settings: ApiSettings) -> list[bytes]:
    if len(uploads) > settings.max_enrollment_files:
        for upload in uploads:
            await upload.close()
        raise ApiError(
            422,
            "too_many_audio_files",
            "The request contains too many enrollment files.",
        )
    payloads: list[bytes] = []
    total = 0
    for upload in uploads:
        payload = await read_upload(upload, settings)
        total += len(payload)
        if total > settings.max_total_upload_bytes:
            raise ApiError(
                413,
                "upload_total_too_large",
                "The combined audio uploads exceed the configured size limit.",
            )
        payloads.append(payload)
    return payloads
