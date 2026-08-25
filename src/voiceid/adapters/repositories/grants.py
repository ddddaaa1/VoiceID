"""Thread-safe in-memory authorization grant repository for tests and demos."""

from __future__ import annotations

import hmac
import threading
from datetime import datetime

from voiceid.domain.authorization import ProtectedAction
from voiceid.domain.grants import AuthorizationGrant, ConsumedAuthorizationGrant


class InMemoryAuthorizationGrantRepository:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._grants: dict[str, tuple[AuthorizationGrant, str, datetime | None]] = {}
        self._nonces: set[tuple[str, str]] = set()

    def issue_grant(self, grant: AuthorizationGrant, token_sha256: str) -> bool:
        with self._lock:
            nonce_key = (grant.device_id, grant.request_nonce)
            if grant.grant_id in self._grants or nonce_key in self._nonces:
                return False
            self._grants[grant.grant_id] = (grant, token_sha256, None)
            self._nonces.add(nonce_key)
            return True

    def consume_grant(
        self,
        *,
        grant_id: str,
        device_id: str,
        action: ProtectedAction,
        token_sha256: str,
        consumed_at: datetime,
    ) -> ConsumedAuthorizationGrant | None:
        with self._lock:
            stored = self._grants.get(grant_id)
            if stored is None:
                return None
            grant, expected_sha256, previous_consumed_at = stored
            if (
                previous_consumed_at is not None
                or consumed_at >= grant.expires_at
                or grant.device_id != device_id
                or grant.action is not action
                or not hmac.compare_digest(expected_sha256, token_sha256)
            ):
                return None
            self._grants[grant_id] = (grant, expected_sha256, consumed_at)
            return ConsumedAuthorizationGrant(
                grant_id=grant.grant_id,
                authorization_id=grant.authorization_id,
                identity_id=grant.identity_id,
                device_id=grant.device_id,
                action=grant.action,
                consumed_at=consumed_at,
            )
