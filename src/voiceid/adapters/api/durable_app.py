"""Environment-configured durable VoiceID ASGI application."""

from __future__ import annotations

import base64
import binascii
import json
import os
from pathlib import Path

from voiceid.domain.grants import validate_device_id

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


def _device_credentials(name: str) -> dict[str, str]:
    encoded = os.environ.get(name)
    if not encoded:
        raise RuntimeError(f"{name} is required")
    try:
        payload = json.loads(encoded)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{name} must be a JSON object") from error
    if not isinstance(payload, dict) or not 1 <= len(payload) <= 1000:
        raise RuntimeError(f"{name} must contain between 1 and 1000 devices")
    credentials: dict[str, str] = {}
    for device_id, credential in payload.items():
        try:
            if not isinstance(device_id, str) or not isinstance(credential, str):
                raise TypeError("device IDs and credentials must be strings")
            validate_device_id(device_id)
            decoded = base64.b64decode(credential, validate=True)
        except (binascii.Error, TypeError, ValueError) as error:
            raise RuntimeError(f"{name} contains an invalid device credential") from error
        if len(decoded) != 32:
            raise RuntimeError(f"{name} credentials must decode to 32 bytes")
        credentials[device_id] = credential
    return credentials


database_path = Path(os.environ.get("VOICEID_DATABASE_PATH", "data/voiceid.sqlite3"))
app = create_app(
    build_durable_container(
        database_path,
        template_encryption_key=_secret("VOICEID_TEMPLATE_KEY", 32),
        audit_hmac_key=_secret("VOICEID_AUDIT_KEY", 32),
        grant_signing_key=_secret("VOICEID_GRANT_KEY", 32),
        device_credentials=_device_credentials("VOICEID_DEVICE_CREDENTIALS"),
    )
)
