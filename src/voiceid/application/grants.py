"""Issue and atomically consume short-lived authorization capabilities."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from voiceid.application.authorization import (
    ActionAuthorizationAttempt,
    ActionAuthorizationService,
)
from voiceid.domain.authorization import AuthorizationDecision, ProtectedAction
from voiceid.domain.governance import AuditEvent
from voiceid.domain.grants import (
    AuthorizationGrant,
    ConsumedAuthorizationGrant,
    validate_device_id,
    validate_grant_request,
)
from voiceid.ports.authorization import AuthorizationGrantRepository, AuthorizationGrantSigner
from voiceid.ports.repositories import AuditRepository, ConsentRepository


class AuthorizationGrantUnavailable(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class AuthorizationGrantIssue:
    authorization: ActionAuthorizationAttempt
    grant: AuthorizationGrant | None
    token: str | None


class AuthorizationGrantService:
    def __init__(
        self,
        authorization: ActionAuthorizationService,
        repository: AuthorizationGrantRepository,
        signer: AuthorizationGrantSigner,
        audit_repository: AuditRepository,
        *,
        consent_repository: ConsentRepository | None = None,
        lifetime: timedelta = timedelta(seconds=30),
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        if not timedelta(seconds=1) <= lifetime <= timedelta(minutes=5):
            raise ValueError("grant lifetime must be between 1 second and 5 minutes")
        self._authorization = authorization
        self._repository = repository
        self._signer = signer
        self._audit = audit_repository
        self._consent = consent_repository
        self._lifetime = lifetime
        self._clock = clock
        self._id_factory = id_factory

    def issue(
        self,
        identity_id: str,
        device_id: str,
        request_nonce: str,
        action: ProtectedAction,
        payload: bytes,
    ) -> AuthorizationGrantIssue:
        device_id, request_nonce = validate_grant_request(device_id, request_nonce)
        authorization = self._authorization.authorize(identity_id, action, payload)
        now = self._clock()
        if authorization.result.decision is not AuthorizationDecision.ALLOW:
            self._audit_decision(authorization, device_id, now, None)
            return AuthorizationGrantIssue(authorization, None, None)

        grant = AuthorizationGrant(
            grant_id=self._id_factory(),
            authorization_id=authorization.authorization_id,
            identity_id=authorization.verification.identity_id,
            device_id=device_id,
            action=action,
            request_nonce=request_nonce,
            issued_at=now,
            expires_at=now + self._lifetime,
        )
        token = self._signer.sign(grant)
        if not self._repository.issue_grant(grant, _token_sha256(token)):
            raise AuthorizationGrantUnavailable("request_nonce_reused")
        self._audit_decision(authorization, device_id, now, grant)
        return AuthorizationGrantIssue(authorization, grant, token)

    def consume(
        self,
        token: str,
        *,
        device_id: str,
        action: ProtectedAction,
    ) -> ConsumedAuthorizationGrant:
        device_id = validate_device_id(device_id)
        now = self._clock()
        try:
            grant = self._signer.verify(token)
        except ValueError as error:
            raise AuthorizationGrantUnavailable("grant_invalid_or_unavailable") from error
        if (
            grant.device_id != device_id
            or grant.action is not action
            or now >= grant.expires_at
            or (self._consent is not None and not self._consent.has_active(grant.identity_id, now))
        ):
            raise AuthorizationGrantUnavailable("grant_invalid_or_unavailable")
        consumed = self._repository.consume_grant(
            grant_id=grant.grant_id,
            device_id=device_id,
            action=action,
            token_sha256=_token_sha256(token),
            consumed_at=now,
        )
        if consumed is None:
            raise AuthorizationGrantUnavailable("grant_invalid_or_unavailable")
        self._audit.append(
            AuditEvent(
                event_id=self._id_factory(),
                identity_id=consumed.identity_id,
                action="authorization_grant_consumed",
                outcome="success",
                created_at=now,
                details=(
                    ("action", consumed.action.value),
                    ("authorization_id", consumed.authorization_id),
                    ("device_id", consumed.device_id),
                    ("grant_id", consumed.grant_id),
                ),
            )
        )
        return consumed

    def _audit_decision(
        self,
        authorization: ActionAuthorizationAttempt,
        device_id: str,
        created_at: datetime,
        grant: AuthorizationGrant | None,
    ) -> None:
        details = [
            ("action", authorization.result.action.value),
            ("authorization_id", authorization.authorization_id),
            ("device_id", device_id),
            ("risk", authorization.result.risk.value),
        ]
        if grant is not None:
            details.extend(
                (("expires_at", grant.expires_at.isoformat()), ("grant_id", grant.grant_id))
            )
        self._audit.append(
            AuditEvent(
                event_id=self._id_factory(),
                identity_id=authorization.verification.identity_id,
                action="authorization_grant_decision",
                outcome=authorization.result.decision.value,
                created_at=created_at,
                details=tuple(details),
            )
        )


def _token_sha256(token: str) -> str:
    try:
        return hashlib.sha256(token.encode("ascii")).hexdigest()
    except UnicodeEncodeError as error:
        raise AuthorizationGrantUnavailable("grant_invalid_or_unavailable") from error
