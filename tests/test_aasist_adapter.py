from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from voiceid.adapters.models.aasist import (
    AasistRuntime,
    AasistSpoofDetector,
    SpoofDetectionError,
)
from voiceid.domain.audio import AudioBuffer


class RecordingRuntime:
    def __init__(self, output: tuple[float, float] = (2.0, -2.0)) -> None:
        self.output = output
        self.received: tuple[float, ...] = ()

    def logits(self, samples: tuple[float, ...]) -> tuple[float, float]:
        self.received = tuple(samples)
        return self.output


def audio(sample_count: int = 16_000, sample_rate: int = 16_000) -> AudioBuffer:
    samples = tuple(
        0.1 * math.sin(2 * math.pi * 220 * index / sample_rate) for index in range(sample_count)
    )
    return AudioBuffer(samples, sample_rate)


class AasistSpoofDetectorTests(unittest.TestCase):
    def test_maps_upstream_logits_to_spoof_probability_and_exact_input_length(self) -> None:
        runtime = RecordingRuntime((2.0, -2.0))
        detector = AasistSpoofDetector(runtime)

        probability = detector.spoof_probability(audio())

        self.assertGreater(probability, 0.98)
        self.assertEqual(len(runtime.received), 64_600)
        self.assertEqual(runtime.received[:16_000], audio().samples)
        self.assertEqual(detector.model_id, "clovaai/aasist-asvspoof2019-la@a04c9863")

    def test_truncates_long_audio_deterministically(self) -> None:
        runtime = RecordingRuntime((-2.0, 2.0))
        source = audio(80_000)
        probability = AasistSpoofDetector(runtime).spoof_probability(source)
        self.assertLess(probability, 0.02)
        self.assertEqual(runtime.received, source.samples[:64_600])

    def test_rejects_wrong_sample_rate_and_non_finite_logits(self) -> None:
        detector = AasistSpoofDetector(RecordingRuntime())
        with self.assertRaisesRegex(SpoofDetectionError, "16 kHz"):
            detector.spoof_probability(audio(sample_rate=8_000))
        with self.assertRaisesRegex(SpoofDetectionError, "non-finite"):
            AasistSpoofDetector(RecordingRuntime((float("nan"), 0.0))).spoof_probability(audio())

    def test_wraps_runtime_failures(self) -> None:
        class FailingRuntime:
            def logits(self, samples: tuple[float, ...]) -> tuple[float, float]:
                raise RuntimeError("internal model path")

        with self.assertRaisesRegex(SpoofDetectionError, "inference failed") as raised:
            AasistSpoofDetector(FailingRuntime()).spoof_probability(audio())
        self.assertNotIn("internal model path", str(raised.exception))

    def test_runtime_rejects_tampered_weights_before_model_loading(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            weights = Path(directory) / "tampered.pth"
            weights.write_bytes(b"not the official checkpoint")
            with self.assertRaisesRegex(SpoofDetectionError, "integrity"):
                AasistRuntime(weights_path=weights).logits(audio().samples)

    def test_official_checkpoint_runs_real_inference(self) -> None:
        probability = AasistSpoofDetector(device="cpu").spoof_probability(audio(64_600))
        self.assertTrue(math.isfinite(probability))
        self.assertGreaterEqual(probability, 0.0)
        self.assertLessEqual(probability, 1.0)


if __name__ == "__main__":
    unittest.main()
