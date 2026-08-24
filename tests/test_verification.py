from __future__ import annotations

import math
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from voiceid.adapters.repositories.memory import InMemoryVoiceTemplateRepository
from voiceid.application.preprocessing import PreprocessingResult
from voiceid.application.verification import VerificationService, VerificationUnavailable
from voiceid.domain.audio import AudioBuffer, PreprocessedAudio, SpeechSegment
from voiceid.domain.enrollment import VoiceTemplate
from voiceid.domain.models import Decision, QualityReport, VerificationPolicy
from voiceid.ports.models import ModelInferenceError

GOOD_QUALITY = QualityReport(3.0, 0.8, 0.001, 24.0)
BAD_QUALITY = QualityReport(0.3, 0.1, 0.08, 1.0)


class FakePreprocessor:
    pipeline_id = "test-pipeline-v1"

    def process(self, payload: bytes) -> PreprocessingResult:
        if payload == b"invalid":
            raise ValueError("decoder internals")
        key = payload[0]
        audio = AudioBuffer((key / 10, key / 10), 16_000)
        processed = PreprocessedAudio(audio, (SpeechSegment(0, 2),))
        return PreprocessingResult(
            processed, BAD_QUALITY if key == 9 else GOOD_QUALITY, audio
        )


class FakeEmbedder:
    model_id = "fake-ecapa-v1"

    def embed(self, audio: PreprocessedAudio) -> tuple[float, ...]:
        key = round(audio.audio.samples[0] * 10)
        if key == 8:
            raise ModelInferenceError("model internals")
        if key == 1:
            return (1.0, 0.0)
        if key == 2:
            return (0.0, 1.0)
        if key == 3:
            return (0.68, math.sqrt(1.0 - 0.68**2))
        if key == 7:
            return (1.0, 0.0, 0.0)
        raise AssertionError(f"unexpected fake sample {key}")


class FakeSpoofDetector:
    model_id = "fake-spoof-v1"

    def __init__(self, probability: float | None) -> None:
        self.probability = probability

    def spoof_probability(self, audio: AudioBuffer) -> float:
        if self.probability is None:
            raise ModelInferenceError("countermeasure internals")
        return self.probability


def template(*, model_id: str = "fake-ecapa-v1") -> VoiceTemplate:
    return VoiceTemplate(
        template_id="template-1",
        identity_id="identity-1",
        embedding=(1.0, 0.0),
        model_id=model_id,
        pipeline_id="test-pipeline-v1",
        version=1,
        sample_count=3,
        created_at=datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
    )


class VerificationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = InMemoryVoiceTemplateRepository()
        self.repository.save(template())

    def service(self, **kwargs) -> VerificationService:
        return VerificationService(
            FakePreprocessor(),
            FakeEmbedder(),
            self.repository,
            clock=lambda: datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
            id_factory=lambda: "attempt-1",
            **kwargs,
        )

    def test_accepts_a_matching_speaker_and_marks_missing_spoof_check(self) -> None:
        attempt = self.service().verify("identity-1", b"\x01")
        self.assertEqual(attempt.result.decision, Decision.ACCEPT)
        self.assertAlmostEqual(attempt.result.speaker_score, 1.0)
        self.assertIsNone(attempt.result.spoof_probability)
        self.assertIsNone(attempt.spoof_model_id)
        self.assertIn("spoof_check_not_run", attempt.result.reasons)
        self.assertEqual(attempt.template_version, 1)
        self.assertEqual(attempt.policy_id, "provisional-cosine-v1")
        self.assertEqual(attempt.attempt_id, "attempt-1")
        self.assertEqual(attempt.created_at, datetime(2026, 8, 24, 13, 0, tzinfo=UTC))

    def test_rejects_a_non_matching_speaker(self) -> None:
        attempt = self.service().verify("identity-1", b"\x02")
        self.assertEqual(attempt.result.decision, Decision.REJECT)
        self.assertIn("speaker_mismatch", attempt.result.reasons)

    def test_reviews_a_borderline_score(self) -> None:
        attempt = self.service().verify("identity-1", b"\x03")
        self.assertEqual(attempt.result.decision, Decision.REVIEW)
        self.assertIn("borderline_speaker_score", attempt.result.reasons)

    def test_reviews_bad_audio_without_running_the_embedder(self) -> None:
        attempt = self.service().verify("identity-1", b"\x09")
        self.assertEqual(attempt.result.decision, Decision.REVIEW)
        self.assertIsNone(attempt.result.speaker_score)
        self.assertIn("insufficient_speech", attempt.result.reasons)

    def test_spoof_probability_overrides_a_speaker_match(self) -> None:
        detector = FakeSpoofDetector(0.95)
        attempt = self.service(spoof_detector=detector).verify("identity-1", b"\x01")
        self.assertEqual(attempt.result.decision, Decision.REJECT)
        self.assertIn("suspected_spoof", attempt.result.reasons)
        self.assertEqual(attempt.spoof_model_id, "fake-spoof-v1")

    def test_reviews_a_non_finite_spoof_score(self) -> None:
        detector = FakeSpoofDetector(float("nan"))
        attempt = self.service(spoof_detector=detector).verify("identity-1", b"\x01")
        self.assertEqual(attempt.result.decision, Decision.REVIEW)
        self.assertEqual(attempt.result.reasons, ("invalid_spoof_score",))

    def test_can_require_an_available_spoof_check(self) -> None:
        policy = VerificationPolicy(require_spoof_check=True)
        attempt = self.service(policy=policy).verify("identity-1", b"\x01")
        self.assertEqual(attempt.result.decision, Decision.REVIEW)
        self.assertEqual(attempt.result.reasons, ("spoof_check_required",))

    def test_reviews_model_and_countermeasure_failures(self) -> None:
        embedding_failure = self.service().verify("identity-1", b"\x08")
        spoof_failure = self.service(spoof_detector=FakeSpoofDetector(None)).verify(
            "identity-1", b"\x01"
        )
        self.assertEqual(embedding_failure.result.reasons, ("speaker_embedding_failed",))
        self.assertEqual(spoof_failure.result.reasons, ("spoof_check_failed",))

    def test_rejects_an_unknown_identity_before_inference(self) -> None:
        with self.assertRaisesRegex(VerificationUnavailable, "active_template_not_found"):
            self.service().verify("missing", b"\x01")

    def test_rejects_invalid_audio_and_model_incompatibility(self) -> None:
        with self.assertRaisesRegex(VerificationUnavailable, "invalid_audio"):
            self.service().verify("identity-1", b"invalid")

        incompatible_repository = InMemoryVoiceTemplateRepository()
        incompatible_repository.save(template(model_id="another-model"))
        service = VerificationService(
            FakePreprocessor(), FakeEmbedder(), incompatible_repository
        )
        with self.assertRaisesRegex(VerificationUnavailable, "speaker_model_mismatch"):
            service.verify("identity-1", b"\x01")

    def test_rejects_incompatible_embedding_dimensions(self) -> None:
        with self.assertRaisesRegex(VerificationUnavailable, "embedding_dimension_mismatch"):
            self.service().verify("identity-1", b"\x07")


if __name__ == "__main__":
    unittest.main()
