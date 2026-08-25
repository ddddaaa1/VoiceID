from __future__ import annotations

import base64
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from fastapi.testclient import TestClient

from voiceid.adapters.api.app import create_app
from voiceid.adapters.api.container import (
    ApiSettings,
    ServiceContainer,
    build_durable_container,
)
from voiceid.application.authorization import ActionAuthorizationAttempt
from voiceid.application.enrollment import (
    EnrollmentRejected,
    EnrollmentResult,
    SampleIssue,
)
from voiceid.application.grants import AuthorizationGrantIssue, AuthorizationGrantUnavailable
from voiceid.application.verification import VerificationAttempt, VerificationUnavailable
from voiceid.domain.authorization import (
    ActionAuthorizationResult,
    ActionRisk,
    AuthorizationDecision,
    ProtectedAction,
)
from voiceid.domain.enrollment import VoiceTemplate
from voiceid.domain.governance import ConsentGrant, RevocationResult
from voiceid.domain.grants import AuthorizationGrant, ConsumedAuthorizationGrant
from voiceid.domain.models import Decision, VerificationResult

CREATED_AT = datetime(2026, 8, 24, 15, 0, tzinfo=UTC)


def voice_template(identity_id: str) -> VoiceTemplate:
    return VoiceTemplate(
        template_id="template-1",
        identity_id=identity_id,
        embedding=(1.0, 0.0),
        model_id="fake-ecapa-v1",
        pipeline_id="fake-audio-v1",
        version=1,
        sample_count=3,
        created_at=CREATED_AT,
    )


class StubEnrollmentService:
    def __init__(self) -> None:
        self.received: tuple[str, list[bytes]] | None = None

    def enroll(self, identity_id: str, samples: list[bytes]) -> EnrollmentResult:
        self.received = identity_id, samples
        if identity_id == "rejected":
            raise EnrollmentRejected(
                "insufficient_valid_samples",
                sample_issues=(SampleIssue(1, ("low_snr",)),),
            )
        return EnrollmentResult(voice_template(identity_id), ())


class StubVerificationService:
    def __init__(self) -> None:
        self.received: tuple[str, bytes] | None = None

    def verify(self, identity_id: str, payload: bytes) -> VerificationAttempt:
        self.received = identity_id, payload
        if identity_id == "missing":
            raise VerificationUnavailable("active_template_not_found")
        return VerificationAttempt(
            attempt_id="attempt-1",
            created_at=CREATED_AT,
            identity_id=identity_id,
            template_id="template-1",
            template_version=1,
            model_id="fake-ecapa-v1",
            spoof_model_id=None,
            pipeline_id="fake-audio-v1",
            policy_id="provisional-cosine-v1",
            result=VerificationResult(
                Decision.ACCEPT,
                0.91,
                None,
                ("speaker_match", "spoof_check_not_run"),
            ),
        )


class StubAuthorizationService:
    def __init__(self, verification: StubVerificationService) -> None:
        self.verification = verification
        self.received: tuple[str, ProtectedAction, bytes] | None = None

    def authorize(
        self,
        identity_id: str,
        action: ProtectedAction,
        payload: bytes,
    ) -> ActionAuthorizationAttempt:
        self.received = identity_id, action, payload
        verification = self.verification.verify(identity_id, payload)
        low_risk = action is ProtectedAction.PLAY_MEDIA
        return ActionAuthorizationAttempt(
            authorization_id="authorization-1",
            created_at=CREATED_AT,
            authorization_policy_id="wearable-action-risk-v1",
            verification=verification,
            result=ActionAuthorizationResult(
                action=action,
                risk=ActionRisk.LOW if low_risk else ActionRisk.HIGH,
                decision=(
                    AuthorizationDecision.ALLOW if low_risk else AuthorizationDecision.STEP_UP
                ),
                reasons=(
                    ("voice_assurance_sufficient",)
                    if low_risk
                    else ("high_risk_action", "device_authentication_required")
                ),
            ),
        )


class StubGrantService:
    def __init__(self, authorization: StubAuthorizationService) -> None:
        self.authorization = authorization
        self.issued = None
        self.consumed = None

    def issue(
        self,
        identity_id: str,
        device_id: str,
        request_nonce: str,
        action: ProtectedAction,
        payload: bytes,
    ) -> AuthorizationGrantIssue:
        self.issued = identity_id, device_id, request_nonce, action, payload
        authorization = self.authorization.authorize(identity_id, action, payload)
        if request_nonce == "nonce-reused-0001":
            raise AuthorizationGrantUnavailable("request_nonce_reused")
        grant = AuthorizationGrant(
            grant_id="grant-1",
            authorization_id=authorization.authorization_id,
            identity_id=identity_id,
            device_id=device_id,
            action=action,
            request_nonce=request_nonce,
            issued_at=CREATED_AT,
            expires_at=datetime(2026, 8, 24, 15, 0, 30, tzinfo=UTC),
        )
        return AuthorizationGrantIssue(authorization, grant, "signed-grant-token")

    def consume(
        self,
        token: str,
        *,
        device_id: str,
        action: ProtectedAction,
    ) -> ConsumedAuthorizationGrant:
        self.consumed = token, device_id, action
        if token == "invalid-token":
            raise AuthorizationGrantUnavailable("grant_invalid_or_unavailable")
        return ConsumedAuthorizationGrant(
            grant_id="grant-1",
            authorization_id="authorization-1",
            identity_id="client-1",
            device_id=device_id,
            action=action,
            consumed_at=CREATED_AT,
        )


class StubDeviceCredentialVerifier:
    def verify(self, device_id: str, credential: str) -> bool:
        return device_id == "wearable-1" and credential == "device-secret"


class StubGovernanceService:
    def grant_consent(
        self,
        identity_id: str,
        *,
        purpose: str,
        notice_version: str,
        expires_at: datetime,
    ) -> ConsentGrant:
        return ConsentGrant(
            consent_id="consent-1",
            identity_id=identity_id,
            purpose=purpose,
            notice_version=notice_version,
            granted_at=CREATED_AT,
            expires_at=expires_at,
        )

    def revoke_identity(self, identity_id: str, *, reason: str) -> RevocationResult:
        self.reason = reason
        return RevocationResult(identity_id, 1, 1, CREATED_AT)


def wave_files(field: str, *payloads: bytes) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        (field, (f"sample-{index}.wav", payload, "audio/wav"))
        for index, payload in enumerate(payloads)
    ]


class ApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.enrollment = StubEnrollmentService()
        self.verification = StubVerificationService()
        self.authorization = StubAuthorizationService(self.verification)
        self.grants = StubGrantService(self.authorization)
        self.governance = StubGovernanceService()
        container = ServiceContainer(
            enrollment=self.enrollment,
            verification=self.verification,
            authorization=self.authorization,  # type: ignore[arg-type]
            settings=ApiSettings(
                max_file_bytes=4,
                max_total_upload_bytes=12,
                max_request_bytes=10_000,
                max_enrollment_files=3,
            ),
            persistence="test-memory",
            speaker_model_id="fake-ecapa-v1",
            governance=self.governance,
            authorization_grants=self.grants,  # type: ignore[arg-type]
            device_credentials=StubDeviceCredentialVerifier(),
            authorization_grants_enabled=True,
        )
        self.client = TestClient(create_app(container))

    def test_health_exposes_runtime_capabilities_without_loading_models(self) -> None:
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["x-request-id"])
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "api_version": "v1",
                "persistence": "test-memory",
                "speaker_model_id": "fake-ecapa-v1",
                "spoof_model_id": None,
                "verification_policy_id": "provisional-cosine-v1",
                "anti_spoofing_enabled": False,
                "authorization_policy_id": "wearable-action-risk-v1",
                "authorization_grants_enabled": True,
            },
        )

    def test_web_experience_and_static_assets_are_served_with_security_headers(self) -> None:
        page = self.client.get("/")
        script = self.client.get("/assets/app.js")
        recorder = self.client.get("/assets/audio-recorder-worklet.js")

        self.assertEqual(page.status_code, 200)
        self.assertIn("Voice action authorization workflow", page.text)
        self.assertEqual(page.headers["x-content-type-options"], "nosniff")
        self.assertIn("default-src 'self'", page.headers["content-security-policy"])
        self.assertEqual(page.headers["permissions-policy"], "microphone=(self)")
        self.assertEqual(script.status_code, 200)
        self.assertIn("javascript", script.headers["content-type"])
        self.assertIn("/api/v1/identities/", script.text)
        self.assertIn("/authorize", script.text)
        self.assertEqual(recorder.status_code, 200)
        self.assertIn("registerProcessor", recorder.text)
        self.assertEqual(self.client.get("/assets/package.json").status_code, 404)

    def test_enrollment_contract(self) -> None:
        response = self.client.post(
            "/api/v1/identities/client-1/enroll",
            files=wave_files("samples", b"one", b"two", b"tri"),
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["identity_id"], "client-1")
        self.assertEqual(body["template_id"], "template-1")
        self.assertEqual(body["retained_samples"], 3)
        self.assertNotIn("embedding", body)
        self.assertEqual(self.enrollment.received, ("client-1", [b"one", b"two", b"tri"]))

    def test_verification_contract(self) -> None:
        response = self.client.post(
            "/api/v1/identities/client-1/verify",
            files=wave_files("sample", b"one"),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["attempt_id"], "attempt-1")
        self.assertEqual(body["decision"], "accept")
        self.assertEqual(body["speaker_score"], 0.91)
        self.assertIsNone(body["spoof_probability"])
        self.assertIsNone(body["spoof_model_id"])
        self.assertIn("spoof_check_not_run", body["reasons"])
        self.assertEqual(self.verification.received, ("client-1", b"one"))
        metrics = self.client.get("/metrics").text
        self.assertIn('route="/api/v1/identities/{identity_id}/verify"', metrics)
        self.assertNotIn("client-1", metrics)

    def test_action_authorization_contract(self) -> None:
        response = self.client.post(
            "/api/v1/identities/client-1/authorize",
            data={"action": "make_purchase"},
            files=wave_files("sample", b"one"),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["authorization_id"], "authorization-1")
        self.assertEqual(body["action"], "make_purchase")
        self.assertEqual(body["risk"], "high")
        self.assertEqual(body["decision"], "step_up")
        self.assertEqual(body["verification"]["attempt_id"], "attempt-1")
        self.assertEqual(
            self.authorization.received,
            ("client-1", ProtectedAction.MAKE_PURCHASE, b"one"),
        )

    def test_action_authorization_rejects_unknown_actions(self) -> None:
        response = self.client.post(
            "/api/v1/identities/client-1/authorize",
            data={"action": "client_selected_low_risk"},
            files=wave_files("sample", b"one"),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "request_validation_failed")

    def test_signed_authorization_grant_issue_and_consumption_contracts(self) -> None:
        headers = {
            "X-VoiceID-Device-ID": "wearable-1",
            "Authorization": "Device device-secret",
        }
        issue_response = self.client.post(
            "/api/v1/identities/client-1/authorization-grants",
            headers=headers,
            data={"action": "play_media", "request_nonce": "nonce-1234567890"},
            files=wave_files("sample", b"one"),
        )

        self.assertEqual(issue_response.status_code, 200)
        self.assertEqual(issue_response.headers["cache-control"], "no-store")
        issue_body = issue_response.json()
        self.assertEqual(issue_body["authorization"]["decision"], "allow")
        self.assertEqual(issue_body["grant"]["grant_id"], "grant-1")
        self.assertEqual(issue_body["grant"]["token"], "signed-grant-token")
        self.assertEqual(
            self.grants.issued,
            (
                "client-1",
                "wearable-1",
                "nonce-1234567890",
                ProtectedAction.PLAY_MEDIA,
                b"one",
            ),
        )

        consume_response = self.client.post(
            "/api/v1/authorization-grants/consume",
            headers=headers,
            json={"token": "signed-grant-token", "action": "play_media"},
        )
        self.assertEqual(consume_response.status_code, 200)
        self.assertEqual(consume_response.json()["grant_id"], "grant-1")
        self.assertEqual(
            self.grants.consumed,
            ("signed-grant-token", "wearable-1", ProtectedAction.PLAY_MEDIA),
        )

    def test_grant_endpoints_require_valid_device_credentials(self) -> None:
        response = self.client.post(
            "/api/v1/authorization-grants/consume",
            headers={
                "X-VoiceID-Device-ID": "wearable-1",
                "Authorization": "Device wrong-secret",
            },
            json={"token": "signed-grant-token", "action": "play_media"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "device_authentication_failed")

    def test_grant_failures_do_not_reveal_consumption_state(self) -> None:
        headers = {
            "X-VoiceID-Device-ID": "wearable-1",
            "Authorization": "Device device-secret",
        }
        invalid = self.client.post(
            "/api/v1/authorization-grants/consume",
            headers=headers,
            json={"token": "invalid-token", "action": "play_media"},
        )
        reused_nonce = self.client.post(
            "/api/v1/identities/client-1/authorization-grants",
            headers=headers,
            data={"action": "play_media", "request_nonce": "nonce-reused-0001"},
            files=wave_files("sample", b"one"),
        )

        self.assertEqual(invalid.status_code, 403)
        self.assertEqual(invalid.json()["error"]["code"], "grant_invalid_or_unavailable")
        self.assertEqual(reused_nonce.status_code, 409)
        self.assertEqual(reused_nonce.json()["error"]["code"], "request_nonce_reused")

    def test_consent_and_revocation_contracts(self) -> None:
        consent_response = self.client.post(
            "/api/v1/identities/client-1/consent",
            json={
                "purpose": "speaker verification",
                "notice_version": "privacy-v1",
                "expires_at": "2026-09-24T15:00:00Z",
            },
        )
        revocation_response = self.client.delete("/api/v1/identities/client-1?reason=user_request")

        self.assertEqual(consent_response.status_code, 201)
        self.assertEqual(consent_response.json()["consent_id"], "consent-1")
        self.assertEqual(revocation_response.status_code, 200)
        self.assertEqual(revocation_response.json()["revoked_templates"], 1)
        self.assertEqual(self.governance.reason, "user_request")

    def test_domain_errors_use_the_stable_error_envelope(self) -> None:
        enrollment_response = self.client.post(
            "/api/v1/identities/rejected/enroll",
            files=wave_files("samples", b"one", b"two", b"tri"),
        )
        verification_response = self.client.post(
            "/api/v1/identities/missing/verify",
            files=wave_files("sample", b"one"),
        )

        self.assertEqual(enrollment_response.status_code, 422)
        self.assertEqual(enrollment_response.json()["error"]["code"], "insufficient_valid_samples")
        self.assertEqual(
            enrollment_response.json()["error"]["details"][0],
            {"sample_index": 1, "reasons": ["low_snr"]},
        )
        self.assertEqual(verification_response.status_code, 404)
        self.assertEqual(verification_response.json()["error"]["code"], "active_template_not_found")

    def test_rejects_unsupported_empty_and_oversized_uploads(self) -> None:
        unsupported = self.client.post(
            "/api/v1/identities/client-1/verify",
            files={"sample": ("sample.mp3", b"abc", "audio/mpeg")},
        )
        empty = self.client.post(
            "/api/v1/identities/client-1/verify",
            files={"sample": ("sample.wav", b"", "audio/wav")},
        )
        oversized = self.client.post(
            "/api/v1/identities/client-1/verify",
            files={"sample": ("sample.wav", b"12345", "audio/wav")},
        )
        self.assertEqual(unsupported.status_code, 415)
        self.assertEqual(unsupported.json()["error"]["code"], "unsupported_media_type")
        self.assertEqual(empty.status_code, 422)
        self.assertEqual(empty.json()["error"]["code"], "empty_audio_file")
        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(oversized.json()["error"]["code"], "file_too_large")

    def test_rejects_too_many_multipart_files_before_reading_them(self) -> None:
        response = self.client.post(
            "/api/v1/identities/client-1/enroll",
            files=wave_files("samples", b"1", b"2", b"3", b"4"),
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "too_many_audio_files")

    def test_rejects_invalid_identity_and_oversized_request_headers(self) -> None:
        invalid_identity = self.client.post(
            "/api/v1/identities/not%20valid/verify",
            files=wave_files("sample", b"one"),
        )
        oversized_request = self.client.post(
            "/api/v1/identities/client-1/verify",
            headers={"content-length": "10001"},
            files=wave_files("sample", b"one"),
        )
        self.assertEqual(invalid_identity.status_code, 422)
        self.assertEqual(invalid_identity.json()["error"]["code"], "request_validation_failed")
        self.assertEqual(oversized_request.status_code, 413)
        self.assertEqual(oversized_request.json()["error"]["code"], "request_too_large")

    def test_openapi_exposes_versioned_operations_and_error_schemas(self) -> None:
        schema = self.client.get("/openapi.json").json()
        self.assertIn("/api/v1/identities/{identity_id}/enroll", schema["paths"])
        self.assertIn("/api/v1/identities/{identity_id}/verify", schema["paths"])
        self.assertIn("/api/v1/identities/{identity_id}/authorize", schema["paths"])
        self.assertIn("/api/v1/identities/{identity_id}/authorization-grants", schema["paths"])
        self.assertIn("/api/v1/authorization-grants/consume", schema["paths"])
        self.assertIn("EnrollmentResponse", schema["components"]["schemas"])
        self.assertIn("VerificationResponse", schema["components"]["schemas"])
        self.assertIn("ActionAuthorizationResponse", schema["components"]["schemas"])
        self.assertIn("AuthorizationGrantIssueResponse", schema["components"]["schemas"])
        self.assertIn("ErrorResponse", schema["components"]["schemas"])


class DurableContainerTests(unittest.TestCase):
    def test_durable_container_enables_grants_without_loading_model_weights(self) -> None:
        credential = base64.b64encode(b"d" * 32).decode("ascii")
        with tempfile.TemporaryDirectory() as directory:
            container = build_durable_container(
                Path(directory) / "voiceid.sqlite3",
                template_encryption_key=b"t" * 32,
                audit_hmac_key=b"a" * 32,
                grant_signing_key=b"g" * 32,
                device_credentials={"wearable-1": credential},
            )

        self.assertTrue(container.authorization_grants_enabled)
        self.assertIsNotNone(container.authorization_grants)
        self.assertTrue(container.device_credentials.verify("wearable-1", credential))


if __name__ == "__main__":
    unittest.main()
