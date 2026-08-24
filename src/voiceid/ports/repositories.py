"""Persistence ports for biometric domain objects."""

from __future__ import annotations

from typing import Protocol

from voiceid.domain.enrollment import VoiceTemplate


class VoiceTemplateRepository(Protocol):
    def get_active(self, identity_id: str) -> VoiceTemplate | None:
        """Return the current template for an identity, if one exists."""

    def save(self, template: VoiceTemplate) -> None:
        """Persist a new active template version."""
