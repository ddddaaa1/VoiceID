from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from voiceid.adapters.repositories.grants import InMemoryAuthorizationGrantRepository
from voiceid.adapters.repositories.sqlite import AesGcmCipher, SqliteBiometricRepository
from voiceid.adapters.security.grants import (
    GrantTokenError,
    HmacGrantSigner,
    StaticDeviceCredentialVerifier,
)
from voiceid.application.authorization import ActionAuthorizationAttempt
from voiceid.application.grants import AuthorizationGrantService, AuthorizationGrantUnavailable
from voiceid.application.verification import VerificationAttempt
from voiceid.domain.authorization import (
    ActionAuthorizationResult,
    ActionRisk,
    AuthorizationDecision,
    ProtectedAction,
)
from voiceid.domain.governance import ConsentGrant
from voiceid.domain.grants import AuthorizationGrant
from voiceid.domain.models import Decision, VerificationResult

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


def grant(*, action: ProtectedAction = ProtectedAction.PLAY_MEDIA) -> AuthorizationGrant:
    return AuthorizationGrant(
        grant_id="grant-1",
        authorization_id="authorization-1",
        identity_id="owner-1",
        device_id="device-1",
        action=action,
        request_nonce="nonce-1234567890",
        issued_at=NOW,
        expires_at=NOW + timedelta(seconds=30),
    )


class GrantTokenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.signer = HmacGrantSigner(b"g" * 32)

    def test_signed_token_round_trip_preserves_all_bindings(self) -> None:
        token = self.signer.sign(grant())

        self.assertEqual(self.signer.verify(token), grant())

    def test_signature_and_payload_tampering_are_rejected(self) -> None:
        token = self.signer.sign(grant())
        encoded, signature = token.split(".")

        with self.assertRaisesRegex(GrantTokenError, "grant_token_invalid"):
            self.signer.verify(f"{encoded[:-1]}A.{signature}")
        changed_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
        with self.assertRaisesRegex(GrantTokenError, "grant_token_invalid"):
            self.signer.verify(f"{encoded}.{changed_signature}")
        with self.assertRaisesRegex(GrantTokenError, "grant_token_invalid"):
            self.signer.verify("not-a-token-ñ")

    def test_device_credentials_use_device_binding_and_constant_time_comparison(self) -> None:
        verifier = StaticDeviceCredentialVerifier({"device-1": "credential-one"})

        self.assertTrue(verifier.verify("device-1", "credential-one"))
        self.assertFalse(verifier.verify("device-1", "credential-two"))
        self.assertFalse(verifier.verify("device-2", "credential-one"))


class StubActionAuthorizationService:
    def __init__(self, decision: AuthorizationDecision = AuthorizationDecision.ALLOW) -> None:
        self.decision = decision

    def authorize(
        self,
        identity_id: str,
        action: ProtectedAction,
        payload: bytes,
    ) -> ActionAuthorizationAttempt:
        verification = VerificationAttempt(
            attempt_id="verification-1",
            created_at=NOW,
            identity_id=identity_id,
            template_id="template-1",
            template_version=1,
            model_id="speaker-v1",
            spoof_model_id=None,
            pipeline_id="audio-v1",
            policy_id="speaker-policy-v1",
            result=VerificationResult(Decision.ACCEPT, 0.91, None, ("speaker_match",)),
        )
        return ActionAuthorizationAttempt(
            authorization_id="authorization-1",
            created_at=NOW,
            authorization_policy_id="action-policy-v1",
            verification=verification,
            result=ActionAuthorizationResult(
                action=action,
                risk=ActionRisk.LOW,
                decision=self.decision,
                reasons=("test_policy",),
            ),
        )


class StubAuditRepository:
    def __init__(self) -> None:
        self.events = []

    def append(self, event) -> None:
        self.events.append(event)


class StubConsentRepository:
    def __init__(self, active: bool) -> None:
        self.active = active

    def has_active(self, identity_id: str, at: datetime) -> bool:
        return self.active


class AuthorizationGrantServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = NOW
        self.repository = InMemoryAuthorizationGrantRepository()
        self.audit = StubAuditRepository()
        self.identifiers = iter(("grant-1", "audit-issue", "audit-consume", "grant-2"))
        self.service = AuthorizationGrantService(
            StubActionAuthorizationService(),  # type: ignore[arg-type]
            self.repository,
            HmacGrantSigner(b"g" * 32),
            self.audit,  # type: ignore[arg-type]
            clock=lambda: self.now,
            id_factory=lambda: next(self.identifiers),
        )

    def test_issued_grant_is_device_action_bound_and_single_use(self) -> None:
        issue = self.service.issue(
            "owner-1",
            "device-1",
            "nonce-1234567890",
            ProtectedAction.PLAY_MEDIA,
            b"wave",
        )

        self.assertIsNotNone(issue.grant)
        self.assertIsNotNone(issue.token)
        consumed = self.service.consume(
            issue.token or "",
            device_id="device-1",
            action=ProtectedAction.PLAY_MEDIA,
        )
        self.assertEqual(consumed.grant_id, "grant-1")
        self.assertEqual(
            [event.action for event in self.audit.events],
            ["authorization_grant_decision", "authorization_grant_consumed"],
        )

        with self.assertRaisesRegex(AuthorizationGrantUnavailable, "grant_invalid_or_unavailable"):
            self.service.consume(
                issue.token or "",
                device_id="device-1",
                action=ProtectedAction.PLAY_MEDIA,
            )

    def test_wrong_device_action_and_expired_tokens_are_indistinguishable(self) -> None:
        issue = self.service.issue(
            "owner-1",
            "device-1",
            "nonce-1234567890",
            ProtectedAction.PLAY_MEDIA,
            b"wave",
        )
        for device_id, action in (
            ("device-2", ProtectedAction.PLAY_MEDIA),
            ("device-1", ProtectedAction.PERSONALIZE_ASSISTANT),
        ):
            with self.assertRaisesRegex(
                AuthorizationGrantUnavailable, "grant_invalid_or_unavailable"
            ):
                self.service.consume(issue.token or "", device_id=device_id, action=action)

        self.now += timedelta(seconds=30)
        with self.assertRaisesRegex(AuthorizationGrantUnavailable, "grant_invalid_or_unavailable"):
            self.service.consume(
                issue.token or "",
                device_id="device-1",
                action=ProtectedAction.PLAY_MEDIA,
            )

    def test_nonce_reuse_is_rejected(self) -> None:
        arguments = (
            "owner-1",
            "device-1",
            "nonce-1234567890",
            ProtectedAction.PLAY_MEDIA,
            b"wave",
        )
        self.service.issue(*arguments)

        with self.assertRaisesRegex(AuthorizationGrantUnavailable, "request_nonce_reused"):
            self.service.issue(*arguments)

    def test_non_allow_decision_is_audited_without_issuing_a_token(self) -> None:
        service = AuthorizationGrantService(
            StubActionAuthorizationService(AuthorizationDecision.STEP_UP),  # type: ignore[arg-type]
            self.repository,
            HmacGrantSigner(b"g" * 32),
            self.audit,  # type: ignore[arg-type]
            clock=lambda: NOW,
            id_factory=lambda: "audit-step-up",
        )

        issue = service.issue(
            "owner-1",
            "device-1",
            "nonce-1234567890",
            ProtectedAction.MAKE_PURCHASE,
            b"wave",
        )

        self.assertIsNone(issue.grant)
        self.assertIsNone(issue.token)
        self.assertEqual(self.audit.events[-1].outcome, "step_up")

    def test_consent_revocation_invalidates_an_unexpired_grant(self) -> None:
        consent = StubConsentRepository(True)
        identifiers = iter(("grant-consent", "audit-consent"))
        service = AuthorizationGrantService(
            StubActionAuthorizationService(),  # type: ignore[arg-type]
            self.repository,
            HmacGrantSigner(b"g" * 32),
            self.audit,  # type: ignore[arg-type]
            consent_repository=consent,  # type: ignore[arg-type]
            clock=lambda: NOW,
            id_factory=lambda: next(identifiers),
        )
        issue = service.issue(
            "owner-1",
            "device-1",
            "nonce-consent-001",
            ProtectedAction.PLAY_MEDIA,
            b"wave",
        )
        consent.active = False

        with self.assertRaisesRegex(AuthorizationGrantUnavailable, "grant_invalid_or_unavailable"):
            service.consume(
                issue.token or "",
                device_id="device-1",
                action=ProtectedAction.PLAY_MEDIA,
            )

    def test_durable_issue_consume_and_audit_chain_work_end_to_end(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SqliteBiometricRepository(
                Path(directory) / "voiceid.sqlite3",
                AesGcmCipher(b"t" * 32),
                audit_hmac_key=b"a" * 32,
            )
            repository.grant(
                ConsentGrant(
                    consent_id="consent-1",
                    identity_id="owner-1",
                    purpose="voice authorization",
                    notice_version="privacy-v1",
                    granted_at=NOW - timedelta(seconds=1),
                    expires_at=NOW + timedelta(days=1),
                )
            )
            identifiers = iter(("grant-durable", "audit-issue", "audit-consume"))
            service = AuthorizationGrantService(
                StubActionAuthorizationService(),  # type: ignore[arg-type]
                repository,
                HmacGrantSigner(b"g" * 32),
                repository,
                consent_repository=repository,
                clock=lambda: NOW,
                id_factory=lambda: next(identifiers),
            )

            issue = service.issue(
                "owner-1",
                "device-1",
                "nonce-durable-001",
                ProtectedAction.PLAY_MEDIA,
                b"wave",
            )
            consumed = service.consume(
                issue.token or "",
                device_id="device-1",
                action=ProtectedAction.PLAY_MEDIA,
            )

            self.assertEqual(consumed.grant_id, "grant-durable")
            self.assertTrue(repository.verify_audit_chain())


if __name__ == "__main__":
    unittest.main()
