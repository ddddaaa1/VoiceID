"""Dependency container for the HTTP adapter."""

from __future__ import annotations

from dataclasses import dataclass, field

from voiceid.adapters.audio.energy_vad import EnergyVoiceActivityDetector
from voiceid.adapters.audio.wave_decoder import PcmWaveDecoder
from voiceid.adapters.models.speechbrain_ecapa import SpeechBrainEcapaEmbedder
from voiceid.adapters.repositories.memory import InMemoryVoiceTemplateRepository
from voiceid.application.enrollment import EnrollmentService
from voiceid.application.preprocessing import AudioPreprocessor
from voiceid.application.verification import VerificationService
from voiceid.domain.models import VerificationPolicy


@dataclass(frozen=True, slots=True)
class ApiSettings:
    max_file_bytes: int = 10_000_000
    max_total_upload_bytes: int = 40_000_000
    max_request_bytes: int = 42_000_000
    max_enrollment_files: int = 8
    allowed_content_types: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {"audio/wav", "audio/x-wav", "audio/wave", "application/octet-stream"}
        )
    )

    def __post_init__(self) -> None:
        if min(
            self.max_file_bytes,
            self.max_total_upload_bytes,
            self.max_request_bytes,
        ) <= 0:
            raise ValueError("API upload limits must be positive")
        if self.max_file_bytes > self.max_total_upload_bytes:
            raise ValueError("per-file limit cannot exceed the total upload limit")
        if self.max_request_bytes < self.max_total_upload_bytes:
            raise ValueError("request limit cannot be lower than the total upload limit")
        if self.max_enrollment_files <= 0:
            raise ValueError("max_enrollment_files must be positive")


@dataclass(frozen=True, slots=True)
class ServiceContainer:
    enrollment: EnrollmentService
    verification: VerificationService
    settings: ApiSettings = field(default_factory=ApiSettings)
    persistence: str = "memory"
    speaker_model_id: str = "speechbrain/spkrec-ecapa-voxceleb"
    spoof_model_id: str | None = None
    verification_policy_id: str = "provisional-cosine-v1"
    anti_spoofing_enabled: bool = False


def build_default_container() -> ServiceContainer:
    preprocessor = AudioPreprocessor(PcmWaveDecoder(), EnergyVoiceActivityDetector())
    embedder = SpeechBrainEcapaEmbedder()
    repository = InMemoryVoiceTemplateRepository()
    policy = VerificationPolicy()
    return ServiceContainer(
        enrollment=EnrollmentService(preprocessor, embedder, repository),
        verification=VerificationService(
            preprocessor,
            embedder,
            repository,
            policy=policy,
        ),
        speaker_model_id=embedder.model_id,
        verification_policy_id=policy.policy_id,
    )
