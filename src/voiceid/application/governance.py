"""Application service for biometric consent, revocation, retention, and audit."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from voiceid.domain.governance import AuditEvent, ConsentGrant, RevocationResult
from voiceid.ports.repositories import AuditRepository, ConsentRepository


class IdentityGovernanceService:
    def __init__(
        self,
        repository: ConsentRepository,
        audit_repository: AuditRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
        maximum_consent_duration: timedelta = timedelta(days=365),
    ) -> None:
        if maximum_consent_duration <= timedelta(0):
            raise ValueError("maximum consent duration must be positive")
        self._repository = repository
        self._audit = audit_repository
        self._clock = clock
        self._id_factory = id_factory
        self._maximum_duration = maximum_consent_duration

    def grant_consent(
        self,
        identity_id: str,
        *,
        purpose: str,
        notice_version: str,
        expires_at: datetime,
    ) -> ConsentGrant:
        now = self._clock()
        if expires_at.tzinfo is None:
            raise ValueError("consent expiration must be timezone-aware")
        if expires_at > now + self._maximum_duration:
            raise ValueError("consent duration exceeds the configured maximum")
        consent = ConsentGrant(
            consent_id=self._id_factory(),
            identity_id=identity_id.strip(),
            purpose=purpose.strip(),
            notice_version=notice_version.strip(),
            granted_at=now,
            expires_at=expires_at,
        )
        self._repository.grant(consent)
        self._audit.append(
            AuditEvent(
                event_id=self._id_factory(),
                identity_id=consent.identity_id,
                action="consent_granted",
                outcome="success",
                created_at=now,
                details=(("notice_version", consent.notice_version),),
            )
        )
        return consent

    def revoke_identity(self, identity_id: str, *, reason: str) -> RevocationResult:
        now = self._clock()
        result = self._repository.revoke_identity(identity_id.strip(), now, reason.strip())
        self._audit.append(
            AuditEvent(
                event_id=self._id_factory(),
                identity_id=result.identity_id,
                action="identity_revoked",
                outcome="success",
                created_at=now,
                details=(
                    ("reason", reason.strip()),
                    ("revoked_consents", str(result.revoked_consents)),
                    ("revoked_templates", str(result.revoked_templates)),
                ),
            )
        )
        return result

    def purge_expired(self) -> int:
        now = self._clock()
        purged = self._repository.purge_expired(now)
        self._audit.append(
            AuditEvent(
                event_id=self._id_factory(),
                identity_id="system",
                action="retention_purge",
                outcome="success",
                created_at=now,
                details=(("purged_templates", str(purged)),),
            )
        )
        return purged
