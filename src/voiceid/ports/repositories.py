"""Persistence ports for biometric domain objects."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from voiceid.domain.enrollment import VoiceTemplate
from voiceid.domain.governance import AuditEvent, ConsentGrant, RevocationResult


class VoiceTemplateRepository(Protocol):
    def get_active(self, identity_id: str) -> VoiceTemplate | None:
        """Return the current template for an identity, if one exists."""

    def save(self, template: VoiceTemplate) -> None:
        """Persist a new active template version."""


class ConsentRepository(Protocol):
    def grant(self, consent: ConsentGrant) -> None:
        """Persist a new active consent grant."""

    def has_active(self, identity_id: str, at: datetime) -> bool:
        """Return whether valid, non-revoked consent exists at a given time."""

    def revoke_identity(
        self, identity_id: str, at: datetime, reason: str
    ) -> RevocationResult:
        """Atomically revoke consents and active templates for an identity."""

    def purge_expired(self, at: datetime) -> int:
        """Purge expired or revoked biometric templates after their retention window."""


class AuditRepository(Protocol):
    def append(self, event: AuditEvent) -> None:
        """Append an immutable, integrity-linked audit event."""
