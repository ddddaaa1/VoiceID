"""Dependency container for the HTTP adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from voiceid.adapters.audio.energy_vad import EnergyVoiceActivityDetector
from voiceid.adapters.audio.wave_decoder import PcmWaveDecoder
from voiceid.adapters.models.speechbrain_ecapa import SpeechBrainEcapaEmbedder
from voiceid.adapters.repositories.memory import InMemoryVoiceTemplateRepository
from voiceid.adapters.repositories.sqlite import AesGcmCipher, SqliteBiometricRepository
from voiceid.application.authorization import ActionAuthorizationService
from voiceid.application.enrollment import EnrollmentService
from voiceid.application.governance import IdentityGovernanceService
from voiceid.application.preprocessing import AudioPreprocessor
from voiceid.application.verification import VerificationService
from voiceid.domain.authorization import ActionAuthorizationPolicy
from voiceid.domain.models import VerificationPolicy


@dataclass(frozen=True, slots=True)
class ApiSettings:
    max_file_bytes: int = 10_000_000
    max_total_upload_bytes: int = 40_000_000
    max_request_bytes: int = 42_000_000
    max_enrollment_files: int = 8
    rate_limit_requests: int = 60
    rate_limit_window_seconds: float = 60.0
    allowed_content_types: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {"audio/wav", "audio/x-wav", "audio/wave", "application/octet-stream"}
        )
    )

    def __post_init__(self) -> None:
        if (
            min(
                self.max_file_bytes,
                self.max_total_upload_bytes,
                self.max_request_bytes,
            )
            <= 0
        ):
            raise ValueError("API upload limits must be positive")
        if self.max_file_bytes > self.max_total_upload_bytes:
            raise ValueError("per-file limit cannot exceed the total upload limit")
        if self.max_request_bytes < self.max_total_upload_bytes:
            raise ValueError("request limit cannot be lower than the total upload limit")
        if self.max_enrollment_files <= 0:
            raise ValueError("max_enrollment_files must be positive")
        if self.rate_limit_requests <= 0 or self.rate_limit_window_seconds <= 0:
            raise ValueError("rate-limit settings must be positive")


@dataclass(frozen=True, slots=True)
class ServiceContainer:
    enrollment: EnrollmentService
    verification: VerificationService
    authorization: ActionAuthorizationService | None = None
    settings: ApiSettings = field(default_factory=ApiSettings)
    persistence: str = "memory"
    speaker_model_id: str = SpeechBrainEcapaEmbedder.MODEL_ID
    spoof_model_id: str | None = None
    verification_policy_id: str = "provisional-cosine-v1"
    anti_spoofing_enabled: bool = False
    authorization_policy_id: str = "wearable-action-risk-v1"
    governance: IdentityGovernanceService | None = None


def build_default_container() -> ServiceContainer:
    preprocessor = AudioPreprocessor(PcmWaveDecoder(), EnergyVoiceActivityDetector())
    embedder = SpeechBrainEcapaEmbedder()
    repository = InMemoryVoiceTemplateRepository()
    policy = VerificationPolicy()
    verification = VerificationService(
        preprocessor,
        embedder,
        repository,
        policy=policy,
    )
    authorization_policy = ActionAuthorizationPolicy()
    return ServiceContainer(
        enrollment=EnrollmentService(preprocessor, embedder, repository),
        verification=verification,
        authorization=ActionAuthorizationService(verification, policy=authorization_policy),
        speaker_model_id=embedder.model_id,
        verification_policy_id=policy.policy_id,
        authorization_policy_id=authorization_policy.policy_id,
    )


def build_durable_container(
    database_path: Path,
    *,
    template_encryption_key: bytes,
    audit_hmac_key: bytes,
    settings: ApiSettings | None = None,
) -> ServiceContainer:
    """Build a consent-gated, encrypted single-node deployment container."""

    preprocessor = AudioPreprocessor(PcmWaveDecoder(), EnergyVoiceActivityDetector())
    embedder = SpeechBrainEcapaEmbedder()
    repository = SqliteBiometricRepository(
        database_path,
        AesGcmCipher(template_encryption_key),
        audit_hmac_key=audit_hmac_key,
    )
    repository.initialize()
    policy = VerificationPolicy()
    verification = VerificationService(
        preprocessor,
        embedder,
        repository,
        consent_repository=repository,
        policy=policy,
    )
    authorization_policy = ActionAuthorizationPolicy()
    governance = IdentityGovernanceService(repository, repository)
    return ServiceContainer(
        enrollment=EnrollmentService(
            preprocessor,
            embedder,
            repository,
            consent_repository=repository,
        ),
        verification=verification,
        authorization=ActionAuthorizationService(verification, policy=authorization_policy),
        settings=settings or ApiSettings(),
        persistence="encrypted-sqlite-v1",
        speaker_model_id=embedder.model_id,
        verification_policy_id=policy.policy_id,
        authorization_policy_id=authorization_policy.policy_id,
        governance=governance,
    )
