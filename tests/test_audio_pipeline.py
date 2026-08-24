from __future__ import annotations

import io
import math
import struct
import sys
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from voiceid.adapters.audio.energy_vad import EnergyVoiceActivityDetector
from voiceid.adapters.audio.wave_decoder import PcmWaveDecoder, WaveDecodingError
from voiceid.application.preprocessing import AudioPreprocessor
from voiceid.domain.audio import AudioBuffer, PreprocessedAudio, SpeechSegment


def wave_payload(
    samples: list[float], *, sample_rate: int = 8_000, channels: int = 1
) -> bytes:
    buffer = io.BytesIO()
    integers = [max(-32768, min(32767, round(sample * 32767))) for sample in samples]
    if channels == 2:
        integers = [value for sample in integers for value in (sample, sample)]
    with wave.open(buffer, "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        target.writeframes(struct.pack(f"<{len(integers)}h", *integers))
    return buffer.getvalue()


class WaveDecoderTests(unittest.TestCase):
    def test_decodes_stereo_pcm_to_normalized_mono(self) -> None:
        decoded = PcmWaveDecoder().decode(wave_payload([0.5, -0.5], channels=2))
        self.assertEqual(decoded.sample_rate, 8_000)
        self.assertEqual(len(decoded.samples), 2)
        self.assertAlmostEqual(decoded.samples[0], 0.5, places=3)

    def test_rejects_invalid_payload(self) -> None:
        with self.assertRaisesRegex(WaveDecodingError, "invalid WAVE"):
            PcmWaveDecoder().decode(b"not audio")

    def test_enforces_duration_limit_before_reading_samples(self) -> None:
        payload = wave_payload([0.0] * 8_000)
        with self.assertRaisesRegex(WaveDecodingError, "duration"):
            PcmWaveDecoder(max_duration_seconds=0.5).decode(payload)


class AudioPreprocessingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = AudioPreprocessor(
            PcmWaveDecoder(),
            EnergyVoiceActivityDetector(threshold_dbfs=-35.0),
        )

    def test_resamples_detects_speech_and_reports_quality(self) -> None:
        sample_rate = 8_000
        silence = [0.0] * 2_000
        tone = [0.4 * math.sin(2 * math.pi * 220 * index / sample_rate) for index in range(4_000)]
        result = self.pipeline.process(wave_payload(silence + tone + silence))

        self.assertEqual(result.processed.audio.sample_rate, 16_000)
        self.assertEqual(result.countermeasure_audio.sample_rate, 16_000)
        self.assertEqual(len(result.processed.audio.samples), 16_000)
        self.assertEqual(len(result.countermeasure_audio.samples), 16_000)
        self.assertEqual(len(result.processed.speech_segments), 1)
        self.assertGreater(result.quality.speech_seconds, 0.45)
        self.assertLess(result.quality.speech_seconds, 0.75)
        self.assertGreater(result.quality.estimated_snr_db, 30.0)
        self.assertLess(
            max(abs(sample) for sample in result.countermeasure_audio.samples),
            max(abs(sample) for sample in result.processed.audio.samples),
        )

    def test_silence_produces_no_speech_segments(self) -> None:
        result = self.pipeline.process(wave_payload([0.0] * 8_000))
        self.assertEqual(result.processed.speech_segments, ())
        self.assertEqual(result.quality.speech_seconds, 0.0)
        self.assertEqual(result.quality.speech_ratio, 0.0)
        self.assertEqual(result.quality.estimated_snr_db, -20.0)

    def test_clipping_is_measured_before_normalization(self) -> None:
        samples = [1.0] * 1_000 + [0.2] * 7_000
        result = self.pipeline.process(wave_payload(samples))
        self.assertAlmostEqual(result.quality.clipping_ratio, 0.125)

    def test_rejects_segments_outside_the_audio_buffer(self) -> None:
        audio = AudioBuffer((0.0, 0.1, 0.0), 16_000)
        with self.assertRaisesRegex(ValueError, "within the audio buffer"):
            PreprocessedAudio(audio, (SpeechSegment(0, 4),))


if __name__ == "__main__":
    unittest.main()
