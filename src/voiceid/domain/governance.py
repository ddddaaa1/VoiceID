"""Consent, revocation, retention, and audit values for biometric identities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ConsentGrant:
    consent_id: str
    identity_id: str
    purpose: str
    notice_version: str
    granted_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        fields = (self.consent_id, self.identity_id, self.purpose, self.notice_version)
        if any(not value or value != value.strip() for value in fields):
            raise ValueError("consent fields must be non-empty")
        if self.granted_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("consent timestamps must be timezone-aware")
        if self.expires_at <= self.granted_at:
            raise ValueError("consent expiration must follow its grant time")


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    identity_id: str
    action: str
    outcome: str
    created_at: datetime
    details: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        fields = (self.event_id, self.identity_id, self.action, self.outcome)
        if any(not value or value != value.strip() for value in fields):
            raise ValueError("audit event fields must be non-empty")
        if self.created_at.tzinfo is None:
            raise ValueError("audit event timestamp must be timezone-aware")
        keys = [key for key, _ in self.details]
        if len(keys) != len(set(keys)) or any(not key for key in keys):
            raise ValueError("audit detail keys must be non-empty and unique")


@dataclass(frozen=True, slots=True)
class RevocationResult:
    identity_id: str
    revoked_templates: int
    revoked_consents: int
    revoked_at: datetime
