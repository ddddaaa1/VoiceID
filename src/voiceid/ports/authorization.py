"""Ports for signed authorization grants and device credentials."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from voiceid.domain.authorization import ProtectedAction
from voiceid.domain.grants import AuthorizationGrant, ConsumedAuthorizationGrant


class AuthorizationGrantSigner(Protocol):
    def sign(self, grant: AuthorizationGrant) -> str: ...

    def verify(self, token: str) -> AuthorizationGrant: ...


class AuthorizationGrantRepository(Protocol):
    def issue_grant(self, grant: AuthorizationGrant, token_sha256: str) -> bool:
        """Persist a grant, returning false when its nonce or ID was already used."""

    def consume_grant(
        self,
        *,
        grant_id: str,
        device_id: str,
        action: ProtectedAction,
        token_sha256: str,
        consumed_at: datetime,
    ) -> ConsumedAuthorizationGrant | None:
        """Atomically consume a matching, unexpired grant exactly once."""


class DeviceCredentialVerifier(Protocol):
    def verify(self, device_id: str, credential: str) -> bool: ...
