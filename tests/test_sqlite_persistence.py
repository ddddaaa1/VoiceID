from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.exceptions import InvalidTag

from voiceid.adapters.repositories.sqlite import AesGcmCipher, SqliteBiometricRepository
from voiceid.application.governance import IdentityGovernanceService
from voiceid.domain.authorization import ProtectedAction
from voiceid.domain.enrollment import VoiceTemplate
from voiceid.domain.governance import AuditEvent, ConsentGrant
from voiceid.domain.grants import AuthorizationGrant

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


class TestCipher:
    """Deterministic authenticated-cipher test double with AAD binding."""

    def encrypt(self, plaintext: bytes, associated_data: bytes) -> tuple[bytes, bytes]:
        tag = associated_data[:8].ljust(8, b"_")
        return b"n" * 12, tag + bytes(value ^ 0xA5 for value in plaintext)

    def decrypt(self, nonce: bytes, ciphertext: bytes, associated_data: bytes) -> bytes:
        if nonce != b"n" * 12 or ciphertext[:8] != associated_data[:8].ljust(8, b"_"):
            raise ValueError("authentication failed")
        return bytes(value ^ 0xA5 for value in ciphertext[8:])


def template(version: int, *, created_at: datetime = NOW) -> VoiceTemplate:
    return VoiceTemplate(
        template_id=f"template-{version}",
        identity_id="identity-1",
        embedding=(1.0, 0.0),
        model_id="model-v1",
        pipeline_id="pipeline-v1",
        version=version,
        sample_count=3,
        created_at=created_at,
    )


def consent(*, expires_at: datetime = NOW + timedelta(days=30)) -> ConsentGrant:
    return ConsentGrant(
        consent_id="consent-1",
        identity_id="identity-1",
        purpose="speaker verification",
        notice_version="privacy-v1",
        granted_at=NOW,
        expires_at=expires_at,
    )


def authorization_grant(*, nonce: str = "nonce-1234567890") -> AuthorizationGrant:
    return AuthorizationGrant(
        grant_id="grant-1",
        authorization_id="authorization-1",
        identity_id="identity-1",
        device_id="device-1",
        action=ProtectedAction.PLAY_MEDIA,
        request_nonce=nonce,
        issued_at=NOW,
        expires_at=NOW + timedelta(seconds=30),
    )


class SqliteBiometricRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "voiceid.sqlite3"
        self.repository = SqliteBiometricRepository(
            self.path,
            TestCipher(),
            audit_hmac_key=b"a" * 32,
            revoked_template_retention=timedelta(days=7),
        )

    def test_templates_survive_restart_and_embeddings_are_not_plaintext(self) -> None:
        self.repository.grant(consent())
        self.repository.save(template(1))

        reopened = SqliteBiometricRepository(
            self.path,
            TestCipher(),
            audit_hmac_key=b"a" * 32,
        )
        self.assertEqual(reopened.get_active("identity-1"), template(1))
        with closing(sqlite3.connect(self.path)) as connection, connection:
            ciphertext = connection.execute(
                "SELECT embedding_ciphertext FROM voice_templates"
            ).fetchone()[0]
        self.assertNotIn(b"[1.0,0.0]", ciphertext)

    def test_reenrollment_versions_and_revocation_are_transactional(self) -> None:
        self.repository.grant(consent())
        self.repository.save(template(1))
        self.repository.save(template(2, created_at=NOW + timedelta(minutes=1)))
        self.assertEqual(self.repository.get_active("identity-1").version, 2)

        result = self.repository.revoke_identity(
            "identity-1", NOW + timedelta(hours=1), "user_request"
        )

        self.assertEqual(result.revoked_templates, 1)
        self.assertEqual(result.revoked_consents, 1)
        self.assertIsNone(self.repository.get_active("identity-1"))
        self.assertFalse(self.repository.has_active("identity-1", NOW + timedelta(hours=1)))

    def test_retention_revokes_expired_consent_then_purges_after_window(self) -> None:
        self.repository.grant(consent(expires_at=NOW + timedelta(days=1)))
        self.repository.save(template(1))
        self.repository.issue_grant(
            authorization_grant(), hashlib.sha256(b"signed-token").hexdigest()
        )

        first = self.repository.purge_expired(NOW + timedelta(days=2))
        second = self.repository.purge_expired(NOW + timedelta(days=10))

        self.assertEqual(first, 0)
        self.assertEqual(second, 1)
        self.assertIsNone(self.repository.get_active("identity-1"))
        with closing(sqlite3.connect(self.path)) as connection, connection:
            grant_count = connection.execute(
                "SELECT COUNT(*) FROM authorization_grants"
            ).fetchone()[0]
        self.assertEqual(grant_count, 0)

    def test_hmac_chain_detects_audit_tampering(self) -> None:
        self.repository.append(
            AuditEvent(
                event_id="event-1",
                identity_id="identity-1",
                action="consent_granted",
                outcome="success",
                created_at=NOW,
            )
        )
        self.repository.append(
            AuditEvent(
                event_id="event-2",
                identity_id="identity-1",
                action="identity_revoked",
                outcome="success",
                created_at=NOW + timedelta(seconds=1),
            )
        )
        self.assertTrue(self.repository.verify_audit_chain())

        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE audit_events SET outcome = 'altered' WHERE event_id = 'event-1'"
            )
        self.assertFalse(self.repository.verify_audit_chain())

    def test_real_aes_gcm_binds_ciphertext_to_template_metadata(self) -> None:
        cipher = AesGcmCipher(b"k" * 32)
        nonce, ciphertext = cipher.encrypt(b"sensitive-template", b"identity-1")

        self.assertEqual(cipher.decrypt(nonce, ciphertext, b"identity-1"), b"sensitive-template")
        with self.assertRaises(InvalidTag):
            cipher.decrypt(nonce, ciphertext, b"different-identity")

    def test_authorization_grant_survives_restart_and_is_consumed_once(self) -> None:
        token_digest = hashlib.sha256(b"signed-token").hexdigest()
        self.assertTrue(self.repository.issue_grant(authorization_grant(), token_digest))

        reopened = SqliteBiometricRepository(
            self.path,
            TestCipher(),
            audit_hmac_key=b"a" * 32,
        )
        consumed = reopened.consume_grant(
            grant_id="grant-1",
            device_id="device-1",
            action=ProtectedAction.PLAY_MEDIA,
            token_sha256=token_digest,
            consumed_at=NOW + timedelta(seconds=1),
        )
        replay = reopened.consume_grant(
            grant_id="grant-1",
            device_id="device-1",
            action=ProtectedAction.PLAY_MEDIA,
            token_sha256=token_digest,
            consumed_at=NOW + timedelta(seconds=2),
        )

        self.assertIsNotNone(consumed)
        self.assertIsNone(replay)

    def test_authorization_grant_rejects_duplicate_device_nonce_and_wrong_binding(self) -> None:
        digest = hashlib.sha256(b"signed-token").hexdigest()
        self.assertTrue(self.repository.issue_grant(authorization_grant(), digest))
        self.assertFalse(self.repository.issue_grant(authorization_grant(), digest))
        self.assertIsNone(
            self.repository.consume_grant(
                grant_id="grant-1",
                device_id="other-device",
                action=ProtectedAction.PLAY_MEDIA,
                token_sha256=digest,
                consumed_at=NOW + timedelta(seconds=1),
            )
        )

    def test_schema_v1_is_migrated_to_authorization_grants_v2(self) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA user_version = 1")

        self.repository.initialize()

        with closing(sqlite3.connect(self.path)) as connection, connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'authorization_grants'"
            ).fetchone()
        self.assertEqual(version, 2)
        self.assertEqual(table[0], "authorization_grants")

    def test_refuses_to_downgrade_an_unknown_future_schema(self) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA user_version = 99")

        with self.assertRaisesRegex(RuntimeError, "unsupported biometric database"):
            self.repository.initialize()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, 99)


class IdentityGovernanceServiceTests(unittest.TestCase):
    def test_grant_and_revoke_are_audited(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SqliteBiometricRepository(
                Path(directory) / "voiceid.sqlite3",
                TestCipher(),
                audit_hmac_key=b"a" * 32,
            )
            identifiers = iter(("consent-1", "audit-1", "audit-2"))
            service = IdentityGovernanceService(
                repository,
                repository,
                clock=lambda: NOW,
                id_factory=lambda: next(identifiers),
            )
            grant = service.grant_consent(
                "identity-1",
                purpose="speaker verification",
                notice_version="privacy-v1",
                expires_at=NOW + timedelta(days=30),
            )
            result = service.revoke_identity("identity-1", reason="user_request")

            self.assertEqual(grant.consent_id, "consent-1")
            self.assertEqual(result.revoked_consents, 1)
            self.assertTrue(repository.verify_audit_chain())


if __name__ == "__main__":
    unittest.main()
