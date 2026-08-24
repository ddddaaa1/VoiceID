from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from fastapi.testclient import TestClient

from voiceid.adapters.api.app import create_app
from voiceid.adapters.api.container import ApiSettings, ServiceContainer
from voiceid.application.enrollment import (
    EnrollmentRejected,
    EnrollmentResult,
    SampleIssue,
)
from voiceid.application.verification import VerificationAttempt, VerificationUnavailable
from voiceid.domain.enrollment import VoiceTemplate
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


def wave_files(field: str, *payloads: bytes) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        (field, (f"sample-{index}.wav", payload, "audio/wav"))
        for index, payload in enumerate(payloads)
    ]


class ApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.enrollment = StubEnrollmentService()
        self.verification = StubVerificationService()
        container = ServiceContainer(
            enrollment=self.enrollment,
            verification=self.verification,
            settings=ApiSettings(
                max_file_bytes=4,
                max_total_upload_bytes=12,
                max_request_bytes=10_000,
                max_enrollment_files=3,
            ),
            persistence="test-memory",
            speaker_model_id="fake-ecapa-v1",
        )
        self.client = TestClient(create_app(container))

    def test_health_exposes_runtime_capabilities_without_loading_models(self) -> None:
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
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
            },
        )

    def test_web_experience_and_static_assets_are_served_with_security_headers(self) -> None:
        page = self.client.get("/")
        script = self.client.get("/assets/app.js")
        recorder = self.client.get("/assets/audio-recorder-worklet.js")

        self.assertEqual(page.status_code, 200)
        self.assertIn("Speaker verification workflow", page.text)
        self.assertEqual(page.headers["x-content-type-options"], "nosniff")
        self.assertIn("default-src 'self'", page.headers["content-security-policy"])
        self.assertEqual(page.headers["permissions-policy"], "microphone=(self)")
        self.assertEqual(script.status_code, 200)
        self.assertIn("javascript", script.headers["content-type"])
        self.assertIn("/api/v1/identities/", script.text)
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
        self.assertEqual(
            enrollment_response.json()["error"]["code"], "insufficient_valid_samples"
        )
        self.assertEqual(
            enrollment_response.json()["error"]["details"][0],
            {"sample_index": 1, "reasons": ["low_snr"]},
        )
        self.assertEqual(verification_response.status_code, 404)
        self.assertEqual(
            verification_response.json()["error"]["code"], "active_template_not_found"
        )

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
        self.assertEqual(
            invalid_identity.json()["error"]["code"], "request_validation_failed"
        )
        self.assertEqual(oversized_request.status_code, 413)
        self.assertEqual(oversized_request.json()["error"]["code"], "request_too_large")

    def test_openapi_exposes_versioned_operations_and_error_schemas(self) -> None:
        schema = self.client.get("/openapi.json").json()
        self.assertIn("/api/v1/identities/{identity_id}/enroll", schema["paths"])
        self.assertIn("/api/v1/identities/{identity_id}/verify", schema["paths"])
        self.assertIn("EnrollmentResponse", schema["components"]["schemas"])
        self.assertIn("VerificationResponse", schema["components"]["schemas"])
        self.assertIn("ErrorResponse", schema["components"]["schemas"])


if __name__ == "__main__":
    unittest.main()
