from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from voiceid.adapters.models.speechbrain_ecapa import (
    SpeakerEmbeddingError,
    SpeechBrainEcapaEmbedder,
)
from voiceid.domain.audio import AudioBuffer, PreprocessedAudio, SpeechSegment


class RecordingRuntime:
    def __init__(self, output: tuple[float, ...] | None = None) -> None:
        self.output = output or tuple(range(1, 193))
        self.received: tuple[float, ...] = ()

    def encode(self, samples: tuple[float, ...]) -> tuple[float, ...]:
        self.received = tuple(samples)
        return self.output


def processed_audio(
    *,
    sample_rate: int = 16_000,
    segments: tuple[SpeechSegment, ...] | None = None,
) -> PreprocessedAudio:
    samples = tuple((index % 100) / 1000 for index in range(sample_rate))
    audio = AudioBuffer(samples, sample_rate)
    return PreprocessedAudio(
        audio,
        segments if segments is not None else (SpeechSegment(0, len(samples)),),
    )


class SpeechBrainEcapaEmbedderTests(unittest.TestCase):
    def test_returns_a_normalized_192_dimension_embedding(self) -> None:
        embedder = SpeechBrainEcapaEmbedder(RecordingRuntime())
        embedding = embedder.embed(processed_audio())
        norm = math.sqrt(sum(value * value for value in embedding))
        self.assertEqual(len(embedding), 192)
        self.assertAlmostEqual(norm, 1.0)
        self.assertEqual(
            embedder.model_id,
            "speechbrain/spkrec-ecapa-voxceleb@0f99f2d0ebe89ac095bcc5903c4dd8f72b367286",
        )

    def test_sends_only_detected_speech_to_the_runtime(self) -> None:
        runtime = RecordingRuntime()
        audio = processed_audio(segments=(SpeechSegment(0, 4_000), SpeechSegment(8_000, 16_000)))
        embedder = SpeechBrainEcapaEmbedder(runtime, min_speech_seconds=0.1)
        embedder.embed(audio)
        self.assertEqual(len(runtime.received), 12_000)

    def test_rejects_audio_without_speech(self) -> None:
        embedder = SpeechBrainEcapaEmbedder(RecordingRuntime())
        with self.assertRaisesRegex(SpeakerEmbeddingError, "does not contain"):
            embedder.embed(processed_audio(segments=()))

    def test_rejects_wrong_sample_rate(self) -> None:
        embedder = SpeechBrainEcapaEmbedder(RecordingRuntime())
        with self.assertRaisesRegex(SpeakerEmbeddingError, "16 kHz"):
            embedder.embed(processed_audio(sample_rate=8_000))

    def test_rejects_unexpected_embedding_dimension(self) -> None:
        embedder = SpeechBrainEcapaEmbedder(RecordingRuntime((1.0, 2.0)))
        with self.assertRaisesRegex(SpeakerEmbeddingError, "192-dimensional"):
            embedder.embed(processed_audio())

    def test_wraps_runtime_errors_without_leaking_framework_details(self) -> None:
        class FailingRuntime:
            def encode(self, samples: tuple[float, ...]) -> tuple[float, ...]:
                raise RuntimeError("internal framework path")

        embedder = SpeechBrainEcapaEmbedder(FailingRuntime())
        with self.assertRaisesRegex(SpeakerEmbeddingError, "inference failed") as raised:
            embedder.embed(processed_audio())
        self.assertNotIn("framework path", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
