"""Encrypted durable biometric repository for a single-node deployment."""

from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import os
import sqlite3
import threading
from collections.abc import Callable
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from voiceid.domain.enrollment import VoiceTemplate
from voiceid.domain.governance import AuditEvent, ConsentGrant, RevocationResult


class AuthenticatedCipher(Protocol):
    def encrypt(self, plaintext: bytes, associated_data: bytes) -> tuple[bytes, bytes]: ...

    def decrypt(self, nonce: bytes, ciphertext: bytes, associated_data: bytes) -> bytes: ...


class AesGcmCipher:
    """AES-256-GCM with a caller-supplied key that is never persisted in SQLite."""

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("AES-GCM key must contain exactly 32 bytes")
        try:
            module = importlib.import_module("cryptography.hazmat.primitives.ciphers.aead")
        except ImportError as error:
            raise RuntimeError(
                "persistence dependencies are missing; install the 'persistence' extra"
            ) from error
        self._cipher = module.AESGCM(key)

    def encrypt(self, plaintext: bytes, associated_data: bytes) -> tuple[bytes, bytes]:
        nonce = os.urandom(12)
        return nonce, self._cipher.encrypt(nonce, plaintext, associated_data)

    def decrypt(self, nonce: bytes, ciphertext: bytes, associated_data: bytes) -> bytes:
        return self._cipher.decrypt(nonce, ciphertext, associated_data)


class SqliteBiometricRepository:
    """Transactional templates, consent, revocation, retention, and chained audit."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        path: Path,
        cipher: AuthenticatedCipher,
        *,
        audit_hmac_key: bytes,
        revoked_template_retention: timedelta = timedelta(days=30),
        connection_factory: Callable[[], sqlite3.Connection] | None = None,
    ) -> None:
        if len(audit_hmac_key) < 32:
            raise ValueError("audit HMAC key must contain at least 32 bytes")
        if revoked_template_retention < timedelta(0):
            raise ValueError("revoked template retention cannot be negative")
        self._path = path
        self._cipher = cipher
        self._audit_hmac_key = audit_hmac_key
        self._retention = revoked_template_retention
        self._connection_factory = connection_factory or self._connect
        self._schema_lock = threading.Lock()
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        with self._schema_lock:
            if self._initialized:
                return
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connection_factory()) as connection, connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version not in {0, self.SCHEMA_VERSION}:
                    raise RuntimeError("unsupported biometric database schema version")
                connection.executescript(_SQLITE_SCHEMA)
                if version == 0:
                    connection.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")
            self._initialized = True

    def get_active(self, identity_id: str) -> VoiceTemplate | None:
        self.initialize()
        with closing(self._connection_factory()) as connection, connection:
            row = connection.execute(
                """SELECT template_id, identity_id, embedding_nonce, embedding_ciphertext,
                          model_id, pipeline_id, version, sample_count, created_at
                   FROM voice_templates
                   WHERE identity_id = ? AND revoked_at IS NULL
                   ORDER BY version DESC LIMIT 1""",
                (identity_id,),
            ).fetchone()
        if row is None:
            return None
        aad = _template_aad(row[1], row[0], row[6], row[4], row[5])
        payload = self._cipher.decrypt(row[2], row[3], aad)
        try:
            embedding_value = json.loads(payload)
            embedding = tuple(float(value) for value in embedding_value)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise RuntimeError("encrypted voice template is invalid") from error
        return VoiceTemplate(
            template_id=row[0],
            identity_id=row[1],
            embedding=embedding,
            model_id=row[4],
            pipeline_id=row[5],
            version=row[6],
            sample_count=row[7],
            created_at=datetime.fromisoformat(row[8]),
        )

    def save(self, template: VoiceTemplate) -> None:
        self.initialize()
        aad = _template_aad(
            template.identity_id,
            template.template_id,
            template.version,
            template.model_id,
            template.pipeline_id,
        )
        payload = json.dumps(template.embedding, separators=(",", ":")).encode("utf-8")
        nonce, ciphertext = self._cipher.encrypt(payload, aad)
        with closing(self._connection_factory()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM voice_templates WHERE identity_id = ?",
                (template.identity_id,),
            ).fetchone()
            expected_version = int(row[0]) + 1
            if template.version != expected_version:
                raise ValueError(
                    f"expected template version {expected_version}, received {template.version}"
                )
            connection.execute(
                """UPDATE voice_templates SET revoked_at = ?, revocation_reason = ?
                   WHERE identity_id = ? AND revoked_at IS NULL""",
                (template.created_at.isoformat(), "superseded", template.identity_id),
            )
            connection.execute(
                """INSERT INTO voice_templates (
                       template_id, identity_id, embedding_nonce, embedding_ciphertext,
                       model_id, pipeline_id, version, sample_count, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    template.template_id,
                    template.identity_id,
                    nonce,
                    ciphertext,
                    template.model_id,
                    template.pipeline_id,
                    template.version,
                    template.sample_count,
                    template.created_at.isoformat(),
                ),
            )

    def grant(self, consent: ConsentGrant) -> None:
        self.initialize()
        with closing(self._connection_factory()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """UPDATE consents SET revoked_at = ?, revocation_reason = ?
                   WHERE identity_id = ? AND revoked_at IS NULL""",
                (consent.granted_at.isoformat(), "superseded", consent.identity_id),
            )
            connection.execute(
                """INSERT INTO consents (
                       consent_id, identity_id, purpose, notice_version, granted_at, expires_at
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    consent.consent_id,
                    consent.identity_id,
                    consent.purpose,
                    consent.notice_version,
                    consent.granted_at.isoformat(),
                    consent.expires_at.isoformat(),
                ),
            )

    def has_active(self, identity_id: str, at: datetime) -> bool:
        _require_aware(at)
        self.initialize()
        with closing(self._connection_factory()) as connection, connection:
            row = connection.execute(
                """SELECT 1 FROM consents
                   WHERE identity_id = ? AND revoked_at IS NULL
                     AND granted_at <= ? AND expires_at > ? LIMIT 1""",
                (identity_id, at.isoformat(), at.isoformat()),
            ).fetchone()
        return row is not None

    def revoke_identity(
        self, identity_id: str, at: datetime, reason: str
    ) -> RevocationResult:
        _require_aware(at)
        if not identity_id or not reason or reason != reason.strip():
            raise ValueError("identity and revocation reason are required")
        self.initialize()
        with closing(self._connection_factory()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            consent_cursor = connection.execute(
                """UPDATE consents SET revoked_at = ?, revocation_reason = ?
                   WHERE identity_id = ? AND revoked_at IS NULL""",
                (at.isoformat(), reason, identity_id),
            )
            template_cursor = connection.execute(
                """UPDATE voice_templates SET revoked_at = ?, revocation_reason = ?
                   WHERE identity_id = ? AND revoked_at IS NULL""",
                (at.isoformat(), reason, identity_id),
            )
        return RevocationResult(
            identity_id=identity_id,
            revoked_templates=template_cursor.rowcount,
            revoked_consents=consent_cursor.rowcount,
            revoked_at=at,
        )

    def purge_expired(self, at: datetime) -> int:
        _require_aware(at)
        self.initialize()
        cutoff = at - self._retention
        with closing(self._connection_factory()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """UPDATE voice_templates SET revoked_at = ?, revocation_reason = ?
                   WHERE revoked_at IS NULL AND NOT EXISTS (
                       SELECT 1 FROM consents
                       WHERE consents.identity_id = voice_templates.identity_id
                         AND consents.revoked_at IS NULL
                         AND consents.granted_at <= ? AND consents.expires_at > ?
                   )""",
                (at.isoformat(), "consent_expired", at.isoformat(), at.isoformat()),
            )
            cursor = connection.execute(
                """DELETE FROM voice_templates
                   WHERE revoked_at IS NOT NULL AND revoked_at <= ?""",
                (cutoff.isoformat(),),
            )
        return cursor.rowcount

    def append(self, event: AuditEvent) -> None:
        self.initialize()
        details = json.dumps(dict(event.details), separators=(",", ":"), sort_keys=True)
        with closing(self._connection_factory()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            previous_hash = previous[0] if previous is not None else "0" * 64
            canonical = (
                f"{previous_hash}|{event.event_id}|{event.identity_id}|{event.action}|"
                f"{event.outcome}|{event.created_at.isoformat()}|{details}"
            ).encode()
            event_hash = hmac.new(
                self._audit_hmac_key, canonical, hashlib.sha256
            ).hexdigest()
            connection.execute(
                """INSERT INTO audit_events (
                       event_id, identity_id, action, outcome, created_at, details_json,
                       previous_hash, event_hash
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_id,
                    event.identity_id,
                    event.action,
                    event.outcome,
                    event.created_at.isoformat(),
                    details,
                    previous_hash,
                    event_hash,
                ),
            )

    def verify_audit_chain(self) -> bool:
        self.initialize()
        with closing(self._connection_factory()) as connection, connection:
            rows = connection.execute(
                """SELECT event_id, identity_id, action, outcome, created_at, details_json,
                          previous_hash, event_hash
                   FROM audit_events ORDER BY sequence"""
            ).fetchall()
        expected_previous = "0" * 64
        for row in rows:
            if row[6] != expected_previous:
                return False
            canonical = "|".join((expected_previous, *row[:6])).encode("utf-8")
            expected = hmac.new(
                self._audit_hmac_key, canonical, hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected, row[7]):
                return False
            expected_previous = row[7]
        return True

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5.0)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection


def _template_aad(
    identity_id: str, template_id: str, version: int, model_id: str, pipeline_id: str
) -> bytes:
    return "|".join(
        ("voiceid-template/v1", identity_id, template_id, str(version), model_id, pipeline_id)
    ).encode("utf-8")


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")


_SQLITE_SCHEMA = """
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS voice_templates (
    template_id TEXT PRIMARY KEY,
    identity_id TEXT NOT NULL,
    embedding_nonce BLOB NOT NULL,
    embedding_ciphertext BLOB NOT NULL,
    model_id TEXT NOT NULL,
    pipeline_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    sample_count INTEGER NOT NULL CHECK (sample_count > 0),
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    revocation_reason TEXT,
    UNIQUE(identity_id, version)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_template_per_identity
ON voice_templates(identity_id) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS consents (
    consent_id TEXT PRIMARY KEY,
    identity_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    notice_version TEXT NOT NULL,
    granted_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    revocation_reason TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_consent_per_identity
ON consents(identity_id) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS audit_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    identity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    outcome TEXT NOT NULL,
    created_at TEXT NOT NULL,
    details_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE
);
"""
