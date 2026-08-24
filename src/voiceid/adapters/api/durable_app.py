"""Environment-configured durable VoiceID ASGI application."""

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path

from .app import create_app
from .container import build_durable_container


def _secret(name: str, expected_bytes: int | None = None) -> bytes:
    encoded = os.environ.get(name)
    if not encoded:
        raise RuntimeError(f"{name} is required")
    try:
        value = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise RuntimeError(f"{name} must be valid base64") from error
    if expected_bytes is not None and len(value) != expected_bytes:
        raise RuntimeError(f"{name} must decode to {expected_bytes} bytes")
    if not value:
        raise RuntimeError(f"{name} cannot be empty")
    return value


database_path = Path(os.environ.get("VOICEID_DATABASE_PATH", "data/voiceid.sqlite3"))
app = create_app(
    build_durable_container(
        database_path,
        template_encryption_key=_secret("VOICEID_TEMPLATE_KEY", 32),
        audit_hmac_key=_secret("VOICEID_AUDIT_KEY", 32),
    )
)
