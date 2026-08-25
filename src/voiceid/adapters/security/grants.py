"""HMAC-signed canonical authorization grant tokens."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from datetime import datetime
from typing import Any

from voiceid.domain.authorization import ProtectedAction
from voiceid.domain.grants import AuthorizationGrant


class GrantTokenError(ValueError):
    pass


class HmacGrantSigner:
    TOKEN_VERSION = 1
    SIGNING_CONTEXT = b"voiceid-authorization-grant/v1."

    def __init__(self, key: bytes) -> None:
        if len(key) < 32:
            raise ValueError("grant signing key must contain at least 32 bytes")
        self._key = key

    def sign(self, grant: AuthorizationGrant) -> str:
        payload = {
            "act": grant.action.value,
            "aid": grant.authorization_id,
            "dev": grant.device_id,
            "exp": grant.expires_at.isoformat(),
            "iat": grant.issued_at.isoformat(),
            "jti": grant.grant_id,
            "nonce": grant.request_nonce,
            "sub": grant.identity_id,
            "ver": self.TOKEN_VERSION,
        }
        encoded = _encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        signature = hmac.new(
            self._key,
            self.SIGNING_CONTEXT + encoded.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return f"{encoded}.{_encode(signature)}"

    def verify(self, token: str) -> AuthorizationGrant:
        if not token or len(token) > 4096 or token != token.strip():
            raise GrantTokenError("grant_token_invalid")
        parts = token.split(".")
        if len(parts) != 2:
            raise GrantTokenError("grant_token_invalid")
        encoded, supplied_signature = parts
        try:
            encoded_bytes = encoded.encode("ascii", errors="strict")
        except UnicodeEncodeError as error:
            raise GrantTokenError("grant_token_invalid") from error
        expected_signature = hmac.new(
            self._key,
            self.SIGNING_CONTEXT + encoded_bytes,
            hashlib.sha256,
        ).digest()
        try:
            decoded_signature = _decode(supplied_signature)
        except (ValueError, UnicodeError) as error:
            raise GrantTokenError("grant_token_invalid") from error
        if not hmac.compare_digest(decoded_signature, expected_signature):
            raise GrantTokenError("grant_token_invalid")
        try:
            payload: Any = json.loads(_decode(encoded))
            if not isinstance(payload, dict) or set(payload) != {
                "act",
                "aid",
                "dev",
                "exp",
                "iat",
                "jti",
                "nonce",
                "sub",
                "ver",
            }:
                raise ValueError
            if payload["ver"] != self.TOKEN_VERSION:
                raise ValueError
            return AuthorizationGrant(
                grant_id=payload["jti"],
                authorization_id=payload["aid"],
                identity_id=payload["sub"],
                device_id=payload["dev"],
                action=ProtectedAction(payload["act"]),
                request_nonce=payload["nonce"],
                issued_at=datetime.fromisoformat(payload["iat"]),
                expires_at=datetime.fromisoformat(payload["exp"]),
            )
        except (KeyError, TypeError, ValueError, UnicodeError) as error:
            raise GrantTokenError("grant_token_invalid") from error


class StaticDeviceCredentialVerifier:
    """Constant-time verification for deployment-injected opaque device credentials."""

    def __init__(self, credentials: dict[str, str]) -> None:
        if not credentials:
            raise ValueError("at least one device credential is required")
        self._digests: dict[str, bytes] = {}
        for device_id, credential in credentials.items():
            if not device_id or not credential or credential != credential.strip():
                raise ValueError("device credentials are invalid")
            self._digests[device_id] = hashlib.sha256(credential.encode("utf-8")).digest()

    def verify(self, device_id: str, credential: str) -> bool:
        expected = self._digests.get(device_id)
        supplied = hashlib.sha256(credential.encode("utf-8")).digest()
        fallback = b"\x00" * hashlib.sha256().digest_size
        return hmac.compare_digest(expected or fallback, supplied) and expected is not None


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    if not value or len(value) % 4 == 1:
        raise ValueError("invalid base64url")
    padding = "=" * (-len(value) % 4)
    try:
        decoded = base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("invalid base64url") from error
    if _encode(decoded) != value:
        raise ValueError("invalid base64url")
    return decoded
