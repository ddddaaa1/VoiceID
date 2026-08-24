"""Lazy, integrity-checked adapter for the official pretrained AASIST model."""

from __future__ import annotations

import hashlib
import importlib
import math
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Protocol

from voiceid.domain.audio import AudioBuffer
from voiceid.ports.models import ModelInferenceError


class SpoofDetectionError(ModelInferenceError):
    """Raised when an AASIST score cannot be produced safely."""


class AasistRuntimeProtocol(Protocol):
    def logits(self, samples: Sequence[float]) -> tuple[float, float]:
        """Return upstream logits ordered as spoof, bonafide."""

    def logits_batch(self, samples: Sequence[Sequence[float]]) -> tuple[tuple[float, float], ...]:
        """Return one upstream logit pair for every waveform."""


@dataclass(frozen=True, slots=True)
class AasistModelScore:
    spoof_logit: float
    bonafide_logit: float
    spoof_probability: float


class AasistRuntime:
    """Load the vendored architecture and checkpoint only on first inference."""

    MODEL_CONFIG: ClassVar[dict[str, object]] = {
        "architecture": "AASIST",
        "nb_samp": 64_600,
        "first_conv": 128,
        "filts": [70, [1, 32], [32, 32], [32, 64], [64, 64]],
        "gat_dims": [64, 32],
        "pool_ratios": [0.5, 0.7, 0.5, 0.5],
        "temperatures": [2.0, 2.0, 100.0, 100.0],
    }
    EXPECTED_WEIGHTS_SHA256 = "51d2d9cf0738172f61e2a384ec50a54a55363240f67c971ed55a92435bc1a1c0"

    def __init__(
        self,
        *,
        weights_path: Path | None = None,
        device: str = "cpu",
    ) -> None:
        if device not in {"cpu", "mps", "cuda"}:
            raise ValueError("AASIST device must be cpu, mps, or cuda")
        self._weights_path = weights_path or Path(__file__).with_name("assets") / "AASIST.pth"
        self._device = device
        self._torch: object | None = None
        self._model: object | None = None
        self._load_lock = threading.Lock()

    def logits(self, samples: Sequence[float]) -> tuple[float, float]:
        return self.logits_batch((samples,))[0]

    def logits_batch(self, samples: Sequence[Sequence[float]]) -> tuple[tuple[float, float], ...]:
        if not samples:
            raise SpoofDetectionError("AASIST batch cannot be empty")
        self._ensure_loaded()
        assert self._torch is not None
        assert self._model is not None
        waveforms = self._torch.tensor(samples, dtype=self._torch.float32).to(self._device)
        with self._torch.inference_mode():
            _, output = self._model(waveforms)
        values = output.detach().cpu().tolist()
        if (
            not isinstance(values, list)
            or len(values) != len(samples)
            or any(not isinstance(item, list) or len(item) != 2 for item in values)
        ):
            raise SpoofDetectionError("AASIST returned an invalid output shape")
        return tuple((float(item[0]), float(item[1])) for item in values)

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            try:
                payload = self._weights_path.read_bytes()
            except OSError as error:
                raise SpoofDetectionError("AASIST weights are unavailable") from error
            digest = hashlib.sha256(payload).hexdigest()
            if digest != self.EXPECTED_WEIGHTS_SHA256:
                raise SpoofDetectionError("AASIST weights failed the integrity check")
            try:
                torch = importlib.import_module("torch")
                architecture = importlib.import_module("voiceid.adapters.models.vendor.aasist")
            except ImportError as error:
                raise SpoofDetectionError(
                    "ML dependencies are missing; install the project with the 'ml' extra"
                ) from error
            try:
                model = architecture.Model(self.MODEL_CONFIG).to(self._device)
                state = torch.load(
                    self._weights_path,
                    map_location=self._device,
                    weights_only=True,
                )
                model.load_state_dict(state)
                model.eval()
            except Exception as error:
                raise SpoofDetectionError("AASIST model loading failed") from error
            self._torch = torch
            self._model = model


class AasistSpoofDetector:
    """Map official AASIST logits to a bounded, uncalibrated spoof estimate."""

    SOURCE_REVISION = "a04c9863f63d44471dde8a6abcb3b082b07cd1d1"
    MODEL_ID = f"clovaai/aasist-asvspoof2019-la@{SOURCE_REVISION[:8]}"
    EXPECTED_SAMPLE_RATE = 16_000
    INPUT_SAMPLES = 64_600

    def __init__(
        self,
        runtime: AasistRuntimeProtocol | None = None,
        *,
        device: str = "cpu",
    ) -> None:
        self._runtime = runtime or AasistRuntime(device=device)

    @property
    def model_id(self) -> str:
        return self.MODEL_ID

    def spoof_probability(self, audio: AudioBuffer) -> float:
        return self.score(audio).spoof_probability

    def score(self, audio: AudioBuffer) -> AasistModelScore:
        samples = self._prepare(audio)
        try:
            logits = self._runtime.logits(samples)
        except SpoofDetectionError:
            raise
        except Exception as error:
            raise SpoofDetectionError("AASIST inference failed") from error
        return _model_score(*logits)

    def score_batch(self, audio: Sequence[AudioBuffer]) -> tuple[AasistModelScore, ...]:
        if not audio:
            raise SpoofDetectionError("AASIST batch cannot be empty")
        samples = tuple(self._prepare(item) for item in audio)
        try:
            logits = self._runtime.logits_batch(samples)
        except SpoofDetectionError:
            raise
        except Exception as error:
            raise SpoofDetectionError("AASIST batch inference failed") from error
        if len(logits) != len(samples):
            raise SpoofDetectionError("AASIST returned an invalid batch size")
        return tuple(_model_score(*item) for item in logits)

    def _prepare(self, audio: AudioBuffer) -> tuple[float, ...]:
        if audio.sample_rate != self.EXPECTED_SAMPLE_RATE:
            raise SpoofDetectionError("AASIST input must be sampled at 16 kHz")
        return _repeat_or_truncate(audio.samples, self.INPUT_SAMPLES)


def _model_score(spoof_logit: float, bonafide_logit: float) -> AasistModelScore:
    if not math.isfinite(spoof_logit) or not math.isfinite(bonafide_logit):
        raise SpoofDetectionError("AASIST returned non-finite logits")
    maximum = max(spoof_logit, bonafide_logit)
    spoof_weight = math.exp(spoof_logit - maximum)
    bonafide_weight = math.exp(bonafide_logit - maximum)
    return AasistModelScore(
        spoof_logit=spoof_logit,
        bonafide_logit=bonafide_logit,
        spoof_probability=spoof_weight / (spoof_weight + bonafide_weight),
    )


def _repeat_or_truncate(samples: Sequence[float], target: int) -> tuple[float, ...]:
    values = tuple(samples)
    if not values:
        raise SpoofDetectionError("AASIST input cannot be empty")
    if len(values) >= target:
        return values[:target]
    repeats = target // len(values) + 1
    return (values * repeats)[:target]
