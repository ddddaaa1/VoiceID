"""Framework-independent audio preprocessing and quality analysis."""

from __future__ import annotations

import math
from dataclasses import dataclass

from voiceid.domain.audio import AudioBuffer, PreprocessedAudio, SpeechSegment
from voiceid.domain.models import QualityReport
from voiceid.ports.audio import AudioDecoder, VoiceActivityDetector


@dataclass(frozen=True, slots=True)
class PreprocessingResult:
    processed: PreprocessedAudio
    quality: QualityReport


class AudioPreprocessor:
    """Decode, resample, normalize, detect speech, and measure signal quality."""

    def __init__(
        self,
        decoder: AudioDecoder,
        vad: VoiceActivityDetector,
        *,
        target_sample_rate: int = 16_000,
        target_peak: float = 0.95,
        pipeline_id: str = "pcm-wave-linear-energy-vad-v1",
    ) -> None:
        if target_sample_rate <= 0:
            raise ValueError("target_sample_rate must be positive")
        if not 0.0 < target_peak <= 1.0:
            raise ValueError("target_peak must be between 0 and 1")
        if not pipeline_id:
            raise ValueError("pipeline_id is required")
        self._decoder = decoder
        self._vad = vad
        self._target_sample_rate = target_sample_rate
        self._target_peak = target_peak
        self._pipeline_id = pipeline_id

    @property
    def pipeline_id(self) -> str:
        return self._pipeline_id

    def process(self, payload: bytes) -> PreprocessingResult:
        decoded = self._decoder.decode(payload)
        clipping_ratio = sum(abs(sample) >= 0.999 for sample in decoded.samples) / len(
            decoded.samples
        )
        resampled = _resample_linear(decoded, self._target_sample_rate)
        normalized = _remove_dc_and_peak_normalize(resampled, self._target_peak)
        segments = self._vad.detect(normalized)
        quality = _quality_report(normalized, segments, clipping_ratio)
        return PreprocessingResult(
            processed=PreprocessedAudio(normalized, segments),
            quality=quality,
        )


def _resample_linear(audio: AudioBuffer, target_rate: int) -> AudioBuffer:
    """Deterministic baseline resampler; production adapters may use soxr/torchaudio."""
    if audio.sample_rate == target_rate:
        return audio
    output_size = max(1, round(len(audio.samples) * target_rate / audio.sample_rate))
    ratio = audio.sample_rate / target_rate
    last_index = len(audio.samples) - 1
    output: list[float] = []
    for output_index in range(output_size):
        position = min(output_index * ratio, last_index)
        left = int(position)
        right = min(left + 1, last_index)
        fraction = position - left
        output.append(audio.samples[left] * (1.0 - fraction) + audio.samples[right] * fraction)
    return AudioBuffer(tuple(output), target_rate)


def _remove_dc_and_peak_normalize(audio: AudioBuffer, target_peak: float) -> AudioBuffer:
    mean = sum(audio.samples) / len(audio.samples)
    centered = tuple(sample - mean for sample in audio.samples)
    peak = max(abs(sample) for sample in centered)
    if peak <= 1e-9:
        return AudioBuffer(tuple(0.0 for _ in centered), audio.sample_rate)
    gain = min(target_peak / peak, 20.0)
    return AudioBuffer(tuple(sample * gain for sample in centered), audio.sample_rate)


def _quality_report(
    audio: AudioBuffer,
    segments: tuple[SpeechSegment, ...],
    clipping_ratio: float,
) -> QualityReport:
    speech_samples = sum(segment.end_sample - segment.start_sample for segment in segments)
    speech_samples = min(speech_samples, len(audio.samples))
    speech_ratio = speech_samples / len(audio.samples)
    speech_power = _segment_power(audio.samples, segments)
    noise_power = _outside_segment_power(audio.samples, segments)

    if speech_power <= 1e-12:
        snr_db = -20.0
    elif noise_power <= 1e-12:
        snr_db = 60.0
    else:
        snr_db = max(-20.0, min(60.0, 10.0 * math.log10(speech_power / noise_power)))

    return QualityReport(
        speech_seconds=speech_samples / audio.sample_rate,
        speech_ratio=speech_ratio,
        clipping_ratio=clipping_ratio,
        estimated_snr_db=snr_db,
    )


def _segment_power(samples: tuple[float, ...], segments: tuple[SpeechSegment, ...]) -> float:
    selected = [
        sample
        for segment in segments
        for sample in samples[segment.start_sample : segment.end_sample]
    ]
    return sum(sample * sample for sample in selected) / len(selected) if selected else 0.0


def _outside_segment_power(
    samples: tuple[float, ...], segments: tuple[SpeechSegment, ...]
) -> float:
    mask = bytearray(len(samples))
    for segment in segments:
        mask[segment.start_sample : segment.end_sample] = b"\x01" * (
            segment.end_sample - segment.start_sample
        )
    selected = [sample for index, sample in enumerate(samples) if not mask[index]]
    return sum(sample * sample for sample in selected) / len(selected) if selected else 0.0
