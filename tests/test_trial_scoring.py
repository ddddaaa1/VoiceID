from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from voiceid.adapters.evaluation.filesystem import HashedAudioFileReader
from voiceid.adapters.evaluation.json_audio_manifest import load_audio_trial_manifest
from voiceid.adapters.evaluation.json_manifest import (
    load_scored_trial_manifest,
    write_scored_trial_manifest,
)
from voiceid.adapters.repositories.memory import InMemoryVoiceTemplateRepository
from voiceid.application.enrollment import EnrollmentService
from voiceid.application.preprocessing import PreprocessingResult
from voiceid.application.trial_scoring import AudioTrialScorer, TrialScoringError
from voiceid.application.verification import VerificationService
from voiceid.domain.audio import AudioBuffer, PreprocessedAudio, SpeechSegment
from voiceid.domain.evaluation import (
    AudioEnrollment,
    AudioFileReference,
    AudioTrial,
    AudioTrialManifest,
    EvaluationProtocolError,
    TrialLabel,
    TrialPartition,
)
from voiceid.domain.models import QualityReport

GOOD_QUALITY = QualityReport(3.0, 0.8, 0.001, 24.0)
BAD_QUALITY = QualityReport(0.2, 0.1, 0.08, 1.0)
SPEAKER_VECTORS = {
    "dev-a": (1.0, 0.0, 0.0, 0.0),
    "dev-b": (0.0, 1.0, 0.0, 0.0),
    "eval-c": (0.0, 0.0, 1.0, 0.0),
    "eval-d": (0.0, 0.0, 0.0, 1.0),
}


def reference(index: int, name: str | None = None) -> AudioFileReference:
    return AudioFileReference(
        path=name or f"audio-{index}.wav",
        sha256=f"{index:064x}",
    )


def enrollment(identity: str, partition: TrialPartition, start_index: int) -> AudioEnrollment:
    return AudioEnrollment(
        identity_id=identity,
        speaker_id=identity,
        partition=partition,
        samples=tuple(reference(start_index + offset) for offset in range(3)),
    )


def audio_manifest() -> AudioTrialManifest:
    enrollments = (
        enrollment("dev-a", TrialPartition.DEVELOPMENT, 1),
        enrollment("dev-b", TrialPartition.DEVELOPMENT, 4),
        enrollment("eval-c", TrialPartition.EVALUATION, 7),
        enrollment("eval-d", TrialPartition.EVALUATION, 10),
    )
    probe_references = {
        "dev-a": reference(13),
        "dev-b": reference(14),
        "eval-c": reference(15),
        "eval-d": reference(16),
    }
    trial_specs = (
        ("dev-g-a", TrialPartition.DEVELOPMENT, "dev-a", "dev-a"),
        ("dev-g-b", TrialPartition.DEVELOPMENT, "dev-b", "dev-b"),
        ("dev-i-a", TrialPartition.DEVELOPMENT, "dev-a", "dev-b"),
        ("dev-i-b", TrialPartition.DEVELOPMENT, "dev-b", "dev-a"),
        ("eval-g-c", TrialPartition.EVALUATION, "eval-c", "eval-c"),
        ("eval-g-d", TrialPartition.EVALUATION, "eval-d", "eval-d"),
        ("eval-i-c", TrialPartition.EVALUATION, "eval-c", "eval-d"),
        ("eval-i-d", TrialPartition.EVALUATION, "eval-d", "eval-c"),
    )
    trials = tuple(
        AudioTrial(
            trial_id=trial_id,
            partition=partition,
            label=(TrialLabel.GENUINE if claimed == probe else TrialLabel.IMPOSTOR),
            claimed_identity_id=claimed,
            probe_speaker_id=probe,
            sample=probe_references[probe],
            condition="clean",
        )
        for trial_id, partition, claimed, probe in trial_specs
    )
    return AudioTrialManifest(
        dataset_id="test-audio-corpus",
        dataset_version="1",
        consent_attestation="All fake speakers are test fixtures.",
        enrollments=enrollments,
        trials=trials,
    )


class MappingAudioReader:
    def __init__(self, payloads: dict[str, bytes]) -> None:
        self.payloads = payloads

    def read(self, reference: AudioFileReference) -> bytes:
        return self.payloads[reference.path]


class FakePreprocessor:
    pipeline_id = "test-pipeline-v1"

    def process(self, payload: bytes) -> PreprocessingResult:
        key = payload.decode()
        quality = BAD_QUALITY if key == "bad-quality" else GOOD_QUALITY
        encoded = tuple(ord(character) / 255 for character in key)
        audio = AudioBuffer(encoded, 16_000)
        return PreprocessingResult(
            PreprocessedAudio(audio, (SpeechSegment(0, len(encoded)),)), quality, audio
        )


class FakeEmbedder:
    model_id = "fake-ecapa-v1"

    def embed(self, audio: PreprocessedAudio) -> tuple[float, ...]:
        key = "".join(chr(round(value * 255)) for value in audio.audio.samples)
        return SPEAKER_VECTORS[key]


def payloads_for(manifest: AudioTrialManifest) -> dict[str, bytes]:
    values: dict[str, bytes] = {}
    for item in manifest.enrollments:
        for sample in item.samples:
            values[sample.path] = item.speaker_id.encode()
    for item in manifest.trials:
        values[item.sample.path] = item.probe_speaker_id.encode()
    return values


class AudioTrialManifestTests(unittest.TestCase):
    def test_example_manifest_is_valid_and_documents_consent(self) -> None:
        path = Path(__file__).parents[1] / "examples" / "evaluation" / "audio-trials.example.json"
        manifest = load_audio_trial_manifest(path)
        self.assertEqual(len(manifest.enrollments), 4)
        self.assertEqual(len(manifest.trials), 8)
        self.assertIn("consent", manifest.consent_attestation.lower())

    def test_rejects_unsafe_paths(self) -> None:
        with self.assertRaisesRegex(EvaluationProtocolError, "safe relative"):
            reference(99, "../outside.wav")

    def test_rejects_audio_content_leakage_between_partitions(self) -> None:
        manifest = audio_manifest()
        trials = list(manifest.trials)
        leaked = trials[0].sample
        original = trials[4]
        trials[4] = AudioTrial(
            trial_id=original.trial_id,
            partition=original.partition,
            label=original.label,
            claimed_identity_id=original.claimed_identity_id,
            probe_speaker_id=original.probe_speaker_id,
            sample=AudioFileReference("leaked.wav", leaked.sha256),
            condition=original.condition,
        )
        with self.assertRaisesRegex(EvaluationProtocolError, "audio content leakage"):
            AudioTrialManifest(
                dataset_id=manifest.dataset_id,
                dataset_version=manifest.dataset_version,
                consent_attestation=manifest.consent_attestation,
                enrollments=manifest.enrollments,
                trials=tuple(trials),
            )


class HashedAudioFileReaderTests(unittest.TestCase):
    def test_reads_a_bounded_file_with_the_expected_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = b"PCM WAVE fixture"
            (base / "sample.wav").write_bytes(payload)
            reference_value = AudioFileReference("sample.wav", hashlib.sha256(payload).hexdigest())
            reader = HashedAudioFileReader(base, max_file_bytes=100)
            self.assertEqual(reader.read(reference_value), payload)

    def test_rejects_checksum_mismatch_and_oversized_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "sample.wav").write_bytes(b"too large")
            mismatch = AudioFileReference("sample.wav", "0" * 64)
            with self.assertRaisesRegex(ValueError, "checksum_mismatch"):
                HashedAudioFileReader(base, max_file_bytes=100).read(mismatch)
            with self.assertRaisesRegex(ValueError, "file_too_large"):
                HashedAudioFileReader(base, max_file_bytes=2).read(mismatch)

    def test_rejects_a_symlink_that_resolves_outside_the_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "dataset"
            base.mkdir()
            outside = root / "outside.wav"
            outside.write_bytes(b"outside")
            (base / "linked.wav").symlink_to(outside)
            linked = AudioFileReference("linked.wav", hashlib.sha256(b"outside").hexdigest())
            with self.assertRaisesRegex(ValueError, "path_outside_dataset"):
                HashedAudioFileReader(base).read(linked)


class AudioTrialScorerTests(unittest.TestCase):
    def test_scores_real_application_services_without_using_decisions_as_labels(self) -> None:
        manifest = audio_manifest()
        repository = InMemoryVoiceTemplateRepository()
        preprocessor = FakePreprocessor()
        embedder = FakeEmbedder()
        scorer = AudioTrialScorer(
            EnrollmentService(preprocessor, embedder, repository),
            VerificationService(preprocessor, embedder, repository),
            MappingAudioReader(payloads_for(manifest)),
        )

        scored = scorer.score(manifest)

        self.assertEqual(scored.model_id, "fake-ecapa-v1")
        self.assertEqual(scored.pipeline_id, "test-pipeline-v1")
        self.assertEqual(len(scored.trials), 8)
        genuine = [item.score for item in scored.trials if item.label is TrialLabel.GENUINE]
        impostor = [item.score for item in scored.trials if item.label is TrialLabel.IMPOSTOR]
        self.assertEqual(genuine, [1.0, 1.0, 1.0, 1.0])
        self.assertEqual(impostor, [0.0, 0.0, 0.0, 0.0])

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "scored.json"
            write_scored_trial_manifest(scored, output)
            self.assertEqual(load_scored_trial_manifest(output), scored)

    def test_fails_the_run_when_a_probe_has_no_score(self) -> None:
        manifest = audio_manifest()
        payloads = payloads_for(manifest)
        payloads[manifest.trials[0].sample.path] = b"bad-quality"
        repository = InMemoryVoiceTemplateRepository()
        preprocessor = FakePreprocessor()
        scorer = AudioTrialScorer(
            EnrollmentService(preprocessor, FakeEmbedder(), repository),
            VerificationService(preprocessor, FakeEmbedder(), repository),
            MappingAudioReader(payloads),
        )
        with self.assertRaisesRegex(TrialScoringError, "score_unavailable"):
            scorer.score(manifest)


if __name__ == "__main__":
    unittest.main()
