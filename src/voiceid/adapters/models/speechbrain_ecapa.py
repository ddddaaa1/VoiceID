"""SpeechBrain ECAPA-TDNN adapter for real speaker embeddings."""

from __future__ import annotations

import importlib
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from voiceid.domain.audio import PreprocessedAudio
from voiceid.domain.scoring import Vector, normalize


class SpeakerEmbeddingError(RuntimeError):
    """Raised when a speaker embedding cannot be produced safely."""


class EcapaRuntime(Protocol):
    def encode(self, samples: Sequence[float]) -> Sequence[float]:
        """Run the concrete ML framework and return one flat embedding."""


class SpeechBrainRuntime:
    """Lazy wrapper around Torch and SpeechBrain.

    Heavy ML libraries and model weights are loaded only when the first embedding
    is requested. Importing the VoiceID domain therefore remains lightweight.
    """

    def __init__(
        self,
        *,
        source: str,
        cache_dir: Path,
        device: str,
    ) -> None:
        self._source = source
        self._cache_dir = cache_dir
        self._device = device
        self._torch: object | None = None
        self._classifier: object | None = None
        self._load_lock = threading.Lock()

    def encode(self, samples: Sequence[float]) -> Sequence[float]:
        self._ensure_loaded()
        assert self._torch is not None
        assert self._classifier is not None

        waveform = self._torch.tensor(samples, dtype=self._torch.float32).unsqueeze(0)
        waveform = waveform.to(self._device)
        with self._torch.inference_mode():
            embedding = self._classifier.encode_batch(waveform)
        return embedding.squeeze().detach().cpu().tolist()

    def _ensure_loaded(self) -> None:
        if self._classifier is not None:
            return
        with self._load_lock:
            if self._classifier is not None:
                return
            try:
                torch = importlib.import_module("torch")
                speaker = importlib.import_module("speechbrain.inference.speaker")
            except ImportError as error:
                raise SpeakerEmbeddingError(
                    "ML dependencies are missing; install the project with the 'ml' extra"
                ) from error

            self._cache_dir.mkdir(parents=True, exist_ok=True)
            classifier_type = speaker.EncoderClassifier
            self._classifier = classifier_type.from_hparams(
                source=self._source,
                savedir=str(self._cache_dir),
                run_opts={"device": self._device},
            )
            self._torch = torch


class SpeechBrainEcapaEmbedder:
    """Convert speech segments into an L2-normalized ECAPA speaker embedding."""

    MODEL_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
    EXPECTED_SAMPLE_RATE = 16_000
    EXPECTED_DIMENSION = 192

    def __init__(
        self,
        runtime: EcapaRuntime | None = None,
        *,
        cache_dir: Path | str = Path("artifacts/models/spkrec-ecapa-voxceleb"),
        device: str = "cpu",
        min_speech_seconds: float = 0.5,
    ) -> None:
        if min_speech_seconds <= 0:
            raise ValueError("min_speech_seconds must be positive")
        self._runtime = runtime or SpeechBrainRuntime(
            source=self.MODEL_SOURCE,
            cache_dir=Path(cache_dir),
            device=device,
        )
        self._min_speech_seconds = min_speech_seconds

    @property
    def model_id(self) -> str:
        return self.MODEL_SOURCE

    def embed(self, audio: PreprocessedAudio) -> Vector:
        if audio.audio.sample_rate != self.EXPECTED_SAMPLE_RATE:
            raise SpeakerEmbeddingError("ECAPA input must be sampled at 16 kHz")
        if not audio.speech_segments:
            raise SpeakerEmbeddingError("ECAPA input does not contain detected speech")

        samples = tuple(
            sample
            for segment in audio.speech_segments
            for sample in audio.audio.samples[segment.start_sample : segment.end_sample]
        )
        duration = len(samples) / audio.audio.sample_rate
        if duration < self._min_speech_seconds:
            raise SpeakerEmbeddingError("ECAPA input contains insufficient speech")

        try:
            raw_embedding = tuple(float(value) for value in self._runtime.encode(samples))
        except SpeakerEmbeddingError:
            raise
        except Exception as error:
            raise SpeakerEmbeddingError("ECAPA inference failed") from error

        if len(raw_embedding) != self.EXPECTED_DIMENSION:
            raise SpeakerEmbeddingError(
                f"expected a {self.EXPECTED_DIMENSION}-dimensional embedding, "
                f"received {len(raw_embedding)}"
            )
        try:
            return normalize(raw_embedding)
        except ValueError as error:
            raise SpeakerEmbeddingError("ECAPA returned an invalid embedding") from error
