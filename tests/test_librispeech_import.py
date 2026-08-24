from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import wave
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from voiceid.adapters.evaluation.json_audio_manifest import load_audio_trial_manifest
from voiceid.adapters.evaluation.librispeech import (
    LibriSpeechCorpusPreparer,
    SoundFilePcmWaveTranscoder,
)
from voiceid.application.librispeech import (
    CorpusPreparationError,
    LibriSpeechClip,
    LibriSpeechImportConfig,
    select_librispeech_clips,
)
from voiceid.domain.evaluation import TrialLabel, TrialPartition


def clip(speaker: str, utterance: int, duration: float = 3.0) -> LibriSpeechClip:
    utterance_id = f"{speaker}-1-{utterance:04d}"
    return LibriSpeechClip(Path(f"/{utterance_id}.flac"), speaker, utterance_id, duration)


class FakeTranscoder:
    def inspect(self, path: Path) -> float:
        return 3.0

    def convert(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.to_pcm_wave_bytes(source))

    def to_pcm_wave_bytes(self, source: Path) -> bytes:
        amplitude = 1000 + hashlib.sha256(source.name.encode()).digest()[0]
        samples = array("h", [0, amplitude, -amplitude] * 16_000)
        with tempfile.NamedTemporaryFile(suffix=".wav") as temporary:
            with wave.open(temporary.name, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16_000)
                wav.writeframes(samples.tobytes())
            return Path(temporary.name).read_bytes()


def build_source_subset(root: Path, subset: str, speakers: tuple[str, ...]) -> Path:
    subset_root = root / "LibriSpeech" / subset
    for speaker in speakers:
        chapter = subset_root / speaker / "1"
        chapter.mkdir(parents=True, exist_ok=True)
        for utterance in range(1, 6):
            (chapter / f"{speaker}-1-{utterance:04d}.flac").write_bytes(b"fixture")
    return subset_root


class LibriSpeechSelectionTests(unittest.TestCase):
    def test_selection_is_deterministic_and_filters_duration(self) -> None:
        config = LibriSpeechImportConfig(
            speakers_per_partition=2,
            probe_clips_per_speaker=1,
            selection_seed="repeatable-test",
        )
        development = tuple(
            clip(speaker, utterance, 1.0 if utterance == 1 else 3.0)
            for speaker in ("1", "2", "3")
            for utterance in range(1, 6)
        )
        evaluation = tuple(
            clip(speaker, utterance) for speaker in ("4", "5", "6") for utterance in range(1, 5)
        )

        first = select_librispeech_clips(development, evaluation, config)
        second = select_librispeech_clips(
            tuple(reversed(development)), tuple(reversed(evaluation)), config
        )

        self.assertEqual(first, second)
        self.assertEqual(len(first), 4)
        self.assertTrue(
            all(
                len(item.enrollment_clips) == 3 and len(item.probe_clips) == 1
                for item in first
            )
        )
        self.assertNotIn("0001", " ".join(
            selected.utterance_id for item in first[:2] for selected in (*item.enrollment_clips, *item.probe_clips)
        ))

    def test_rejects_speaker_overlap_and_insufficient_cohort(self) -> None:
        config = LibriSpeechImportConfig(speakers_per_partition=2, probe_clips_per_speaker=1)
        enough = tuple(clip(speaker, index) for speaker in ("1", "2") for index in range(4))
        with self.assertRaisesRegex(CorpusPreparationError, "share speakers"):
            select_librispeech_clips(enough, enough, config)

        too_small = tuple(clip("3", index) for index in range(4))
        with self.assertRaisesRegex(CorpusPreparationError, "eligible speakers"):
            select_librispeech_clips(enough, too_small, config)

    def test_pipeline_filter_replaces_rejected_clips_deterministically(self) -> None:
        config = LibriSpeechImportConfig(
            speakers_per_partition=2,
            probe_clips_per_speaker=1,
            selection_seed="quality-filter-test",
        )
        development = tuple(
            clip(speaker, index) for speaker in ("1", "2") for index in range(8)
        )
        evaluation = tuple(
            clip(speaker, index) for speaker in ("3", "4") for index in range(8)
        )
        rejected = {
            select_librispeech_clips(development, evaluation, config)[0]
            .enrollment_clips[0]
            .utterance_id
        }

        selected = select_librispeech_clips(
            development,
            evaluation,
            config,
            lambda candidate: candidate.utterance_id not in rejected,
        )

        used = {
            candidate.utterance_id
            for speaker in selected
            for candidate in (*speaker.enrollment_clips, *speaker.probe_clips)
        }
        self.assertTrue(rejected.isdisjoint(used))
        self.assertEqual(len(used), 16)


class LibriSpeechCorpusPreparerTests(unittest.TestCase):
    def test_prepares_balanced_hash_locked_manifest_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            development = build_source_subset(root, "dev-clean", ("1", "2"))
            evaluation = build_source_subset(root, "test-clean", ("3", "4"))
            output = root / "prepared"
            config = LibriSpeechImportConfig(
                speakers_per_partition=2,
                enrollment_clips_per_speaker=3,
                probe_clips_per_speaker=2,
            )

            generated = LibriSpeechCorpusPreparer(FakeTranscoder()).prepare(
                development,
                evaluation,
                output,
                dataset_version="test-v1",
                config=config,
            )
            loaded = load_audio_trial_manifest(output / "audio-trials.json")

            self.assertEqual(loaded, generated)
            self.assertEqual(len(loaded.enrollments), 4)
            self.assertEqual(len(loaded.trials), 16)
            for partition in TrialPartition:
                partition_trials = [
                    trial for trial in loaded.trials if trial.partition is partition
                ]
                self.assertEqual(
                    sum(trial.label is TrialLabel.GENUINE for trial in partition_trials), 4
                )
                self.assertEqual(
                    sum(trial.label is TrialLabel.IMPOSTOR for trial in partition_trials), 4
                )

            for enrollment in loaded.enrollments:
                for reference in enrollment.samples:
                    payload = (output / reference.path).read_bytes()
                    self.assertEqual(hashlib.sha256(payload).hexdigest(), reference.sha256)

            provenance = json.loads((output / "provenance.json").read_text())
            self.assertEqual(provenance["source"]["license"], "CC BY 4.0")
            self.assertEqual(provenance["protocol"]["development_subset"], "dev-clean")
            self.assertEqual(provenance["protocol"]["evaluation_subset"], "test-clean")
            self.assertEqual(
                hashlib.sha256((output / "audio-trials.json").read_bytes()).hexdigest(),
                provenance["manifest_sha256"],
            )

            with self.assertRaisesRegex(CorpusPreparationError, "must not already exist"):
                LibriSpeechCorpusPreparer(FakeTranscoder()).prepare(
                    development,
                    evaluation,
                    output,
                    dataset_version="test-v1",
                    config=config,
                )

    def test_soundfile_transcoder_writes_supported_pcm_wave(self) -> None:
        try:
            import soundfile
        except ImportError:
            self.skipTest("soundfile is only installed with the ML environment")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.flac"
            destination = root / "destination.wav"
            samples = array("h", [0, 1000, -1000] * 16_000)
            soundfile.write(source, samples, 16_000, format="FLAC", subtype="PCM_16")

            transcoder = SoundFilePcmWaveTranscoder()
            self.assertEqual(transcoder.inspect(source), 3.0)
            transcoder.convert(source, destination)

            with wave.open(str(destination), "rb") as wav:
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getframerate(), 16_000)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getnframes(), 48_000)


if __name__ == "__main__":
    unittest.main()
