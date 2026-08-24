"""Thread-safe in-memory repository for tests and local development."""

from __future__ import annotations

import threading

from voiceid.domain.enrollment import VoiceTemplate


class InMemoryVoiceTemplateRepository:
    def __init__(self) -> None:
        self._templates: dict[str, VoiceTemplate] = {}
        self._lock = threading.RLock()

    def get_active(self, identity_id: str) -> VoiceTemplate | None:
        with self._lock:
            return self._templates.get(identity_id)

    def save(self, template: VoiceTemplate) -> None:
        with self._lock:
            current = self._templates.get(template.identity_id)
            expected_version = 1 if current is None else current.version + 1
            if template.version != expected_version:
                raise ValueError(
                    f"expected template version {expected_version}, received {template.version}"
                )
            self._templates[template.identity_id] = template
