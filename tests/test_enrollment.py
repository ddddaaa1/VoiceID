from __future__ import annotations

import math
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from voiceid.adapters.repositories.memory import InMemoryVoiceTemplateRepository
from voiceid.application.enrollment import EnrollmentRejected, EnrollmentService
from voiceid.application.preprocessing import PreprocessingResult
from voiceid.domain.audio import AudioBuffer, PreprocessedAudio, SpeechSegment
from voiceid.domain.models import QualityReport
from voiceid.ports.models import ModelInferenceError

GOOD_QUALITY = QualityReport(3.0, 0.8, 0.001, 24.0)
BAD_QUALITY = QualityReport(0.4, 0.1, 0.08, 2.0)
EMBEDDINGS = {
    1: (1.0, 0.01),
    2: (0.99, 0.02),
    3: (1.0, -0.02),
    4: (-1.0, 0.0),
    5: (0.0, 1.0),
}


class FakePreprocessor:
    pipeline_id = "test-pipeline-v1"

    def process(self, payload: bytes) -> PreprocessingResult:
        if payload == b"invalid":
            raise ValueError("decoder details")
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
            raise ModelInferenceError("runtime details")
        return EMBEDDINGS[key]


class EnrollmentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = InMemoryVoiceTemplateRepository()
        self.identifiers = iter(("template-1", "template-2"))
        self.service = EnrollmentService(
            FakePreprocessor(),
            FakeEmbedder(),
            self.repository,
            clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
            id_factory=lambda: next(self.identifiers),
        )

    def test_enrolls_consistent_samples_and_discards_an_outlier(self) -> None:
        result = self.service.enroll("identity-1", [b"\x01", b"\x02", b"\x03", b"\x04"])

        self.assertEqual(result.template.template_id, "template-1")
        self.assertEqual(result.template.identity_id, "identity-1")
        self.assertEqual(result.template.model_id, "fake-ecapa-v1")
        self.assertEqual(result.template.pipeline_id, "test-pipeline-v1")
        self.assertEqual(result.template.sample_count, 3)
        self.assertEqual(result.template.version, 1)
        self.assertAlmostEqual(
            math.sqrt(sum(value * value for value in result.template.embedding)), 1.0
        )
        self.assertEqual(result.discarded_samples[0].sample_index, 3)
        self.assertEqual(result.discarded_samples[0].reasons, ("inconsistent_voice",))
        self.assertEqual(self.repository.get_active("identity-1"), result.template)

    def test_reenrollment_creates_a_new_template_version(self) -> None:
        samples = [b"\x01", b"\x02", b"\x03"]
        first = self.service.enroll("identity-1", samples)
        second = self.service.enroll("identity-1", samples)
        self.assertEqual(first.template.version, 1)
        self.assertEqual(second.template.version, 2)
        self.assertEqual(second.template.template_id, "template-2")

    def test_rejects_too_few_submitted_samples(self) -> None:
        with self.assertRaisesRegex(EnrollmentRejected, "insufficient_submitted_samples"):
            self.service.enroll("identity-1", [b"\x01", b"\x02"])

    def test_reports_quality_and_decoder_failures(self) -> None:
        with self.assertRaises(EnrollmentRejected) as raised:
            self.service.enroll("identity-1", [b"\x01", b"\x09", b"invalid"])

        self.assertEqual(raised.exception.code, "insufficient_valid_samples")
        issue_indices = tuple(issue.sample_index for issue in raised.exception.sample_issues)
        self.assertEqual(issue_indices, (1, 2))
        self.assertIn("insufficient_speech", raised.exception.sample_issues[0].reasons)
        self.assertEqual(raised.exception.sample_issues[1].reasons, ("invalid_audio",))

    def test_reports_model_inference_failure_without_leaking_details(self) -> None:
        with self.assertRaises(EnrollmentRejected) as raised:
            self.service.enroll("identity-1", [b"\x01", b"\x02", b"\x08"])
        self.assertEqual(raised.exception.code, "insufficient_valid_samples")
        self.assertEqual(raised.exception.sample_issues[0].reasons, ("embedding_failed",))

    def test_rejects_mutually_inconsistent_speakers(self) -> None:
        with self.assertRaises(EnrollmentRejected) as raised:
            self.service.enroll("identity-1", [b"\x01", b"\x04", b"\x05"])
        self.assertEqual(raised.exception.code, "inconsistent_speakers")

    def test_requires_an_identity_id(self) -> None:
        with self.assertRaisesRegex(EnrollmentRejected, "identity_id_required"):
            self.service.enroll("  ", [b"\x01", b"\x02", b"\x03"])


if __name__ == "__main__":
    unittest.main()
