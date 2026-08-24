"""Application service for one-to-one speaker verification."""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from voiceid.domain.decision import decide, evaluate_quality
from voiceid.domain.enrollment import VoiceTemplate
from voiceid.domain.models import Decision, VerificationPolicy, VerificationResult
from voiceid.domain.scoring import cosine_similarity
from voiceid.ports.models import ModelInferenceError, SpeakerEmbedder, SpoofDetector
from voiceid.ports.repositories import ConsentRepository, VoiceTemplateRepository

from .enrollment import PreprocessingService


@dataclass(frozen=True, slots=True)
class VerificationAttempt:
    attempt_id: str
    created_at: datetime
    identity_id: str
    template_id: str
    template_version: int
    model_id: str
    spoof_model_id: str | None
    pipeline_id: str
    policy_id: str
    result: VerificationResult


class VerificationUnavailable(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class VerificationService:
    def __init__(
        self,
        preprocessor: PreprocessingService,
        embedder: SpeakerEmbedder,
        repository: VoiceTemplateRepository,
        *,
        consent_repository: ConsentRepository | None = None,
        spoof_detector: SpoofDetector | None = None,
        policy: VerificationPolicy | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self._preprocessor = preprocessor
        self._embedder = embedder
        self._repository = repository
        self._consent_repository = consent_repository
        self._spoof_detector = spoof_detector
        self._policy = policy or VerificationPolicy()
        self._clock = clock
        self._id_factory = id_factory

    def verify(self, identity_id: str, payload: bytes) -> VerificationAttempt:
        identity_id = identity_id.strip()
        if not identity_id:
            raise VerificationUnavailable("identity_id_required")
        if self._consent_repository is not None and not self._consent_repository.has_active(
            identity_id, self._clock()
        ):
            raise VerificationUnavailable("active_consent_required")

        template = self._repository.get_active(identity_id)
        if template is None:
            raise VerificationUnavailable("active_template_not_found")
        if template.model_id != self._embedder.model_id:
            raise VerificationUnavailable("speaker_model_mismatch")
        if template.pipeline_id != self._preprocessor.pipeline_id:
            raise VerificationUnavailable("audio_pipeline_mismatch")

        try:
            preprocessing = self._preprocessor.process(payload)
        except ValueError as error:
            raise VerificationUnavailable("invalid_audio") from error

        quality_reasons = evaluate_quality(preprocessing.quality, self._policy)
        if quality_reasons:
            return self._attempt(
                template,
                VerificationResult(Decision.REVIEW, None, None, quality_reasons),
            )

        try:
            probe_embedding = self._embedder.embed(preprocessing.processed)
        except ModelInferenceError:
            return self._attempt(
                template,
                VerificationResult(
                    Decision.REVIEW,
                    None,
                    None,
                    ("speaker_embedding_failed",),
                ),
            )

        try:
            speaker_score = cosine_similarity(template.embedding, probe_embedding)
        except ValueError as error:
            raise VerificationUnavailable("embedding_dimension_mismatch") from error

        spoof_probability: float | None = None
        if self._spoof_detector is not None:
            try:
                spoof_probability = self._spoof_detector.spoof_probability(
                    preprocessing.countermeasure_audio
                )
            except ModelInferenceError:
                return self._attempt(
                    template,
                    VerificationResult(
                        Decision.REVIEW,
                        speaker_score,
                        None,
                        ("spoof_check_failed",),
                    ),
                )
            if not math.isfinite(spoof_probability) or not 0.0 <= spoof_probability <= 1.0:
                return self._attempt(
                    template,
                    VerificationResult(
                        Decision.REVIEW,
                        speaker_score,
                        None,
                        ("invalid_spoof_score",),
                    ),
                )

        result = decide(
            speaker_score=speaker_score,
            spoof_probability=spoof_probability,
            quality=preprocessing.quality,
            policy=self._policy,
        )
        return self._attempt(template, result)

    def _attempt(
        self, template: VoiceTemplate, result: VerificationResult
    ) -> VerificationAttempt:
        return VerificationAttempt(
            attempt_id=self._id_factory(),
            created_at=self._clock(),
            identity_id=template.identity_id,
            template_id=template.template_id,
            template_version=template.version,
            model_id=template.model_id,
            spoof_model_id=(
                self._spoof_detector.model_id if self._spoof_detector is not None else None
            ),
            pipeline_id=template.pipeline_id,
            policy_id=self._policy.policy_id,
            result=result,
        )
