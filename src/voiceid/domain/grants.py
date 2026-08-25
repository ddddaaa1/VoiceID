"""Short-lived, device-bound authorization grant values."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from .authorization import ProtectedAction

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
NONCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{15,127}$")


def validate_device_id(device_id: str) -> str:
    device_id = device_id.strip()
    if not IDENTIFIER_PATTERN.fullmatch(device_id):
        raise ValueError("device_id is invalid")
    return device_id


def validate_grant_request(device_id: str, request_nonce: str) -> tuple[str, str]:
    device_id = validate_device_id(device_id)
    request_nonce = request_nonce.strip()
    if not NONCE_PATTERN.fullmatch(request_nonce):
        raise ValueError("request_nonce must contain 16 to 128 URL-safe characters")
    return device_id, request_nonce


@dataclass(frozen=True, slots=True)
class AuthorizationGrant:
    grant_id: str
    authorization_id: str
    identity_id: str
    device_id: str
    action: ProtectedAction
    request_nonce: str
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        identifiers = (
            self.grant_id,
            self.authorization_id,
            self.identity_id,
            self.device_id,
        )
        if any(not IDENTIFIER_PATTERN.fullmatch(value) for value in identifiers):
            raise ValueError("grant identifiers are invalid")
        validate_grant_request(self.device_id, self.request_nonce)
        if self.issued_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("grant timestamps must be timezone-aware")
        if self.expires_at <= self.issued_at:
            raise ValueError("grant expiration must follow issue time")


@dataclass(frozen=True, slots=True)
class ConsumedAuthorizationGrant:
    grant_id: str
    authorization_id: str
    identity_id: str
    device_id: str
    action: ProtectedAction
    consumed_at: datetime

    def __post_init__(self) -> None:
        if self.consumed_at.tzinfo is None:
            raise ValueError("consumption timestamp must be timezone-aware")
