"""Application service for multi-sample speaker enrollment."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from voiceid.domain.decision import evaluate_quality
from voiceid.domain.enrollment import EnrollmentPolicy, VoiceTemplate
from voiceid.domain.scoring import build_robust_voice_template
from voiceid.ports.models import ModelInferenceError, SpeakerEmbedder
from voiceid.ports.repositories import ConsentRepository, VoiceTemplateRepository

from .preprocessing import PreprocessingResult


class PreprocessingService(Protocol):
    @property
    def pipeline_id(self) -> str: ...

    def process(self, payload: bytes) -> PreprocessingResult: ...


@dataclass(frozen=True, slots=True)
class SampleIssue:
    sample_index: int
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EnrollmentResult:
    template: VoiceTemplate
    discarded_samples: tuple[SampleIssue, ...]


class EnrollmentRejected(ValueError):
    def __init__(
        self,
        code: str,
        *,
        sample_issues: tuple[SampleIssue, ...] = (),
    ) -> None:
        super().__init__(code)
        self.code = code
        self.sample_issues = sample_issues


class EnrollmentService:
    def __init__(
        self,
        preprocessor: PreprocessingService,
        embedder: SpeakerEmbedder,
        repository: VoiceTemplateRepository,
        *,
        consent_repository: ConsentRepository | None = None,
        policy: EnrollmentPolicy | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self._preprocessor = preprocessor
        self._embedder = embedder
        self._repository = repository
        self._consent_repository = consent_repository
        self._policy = policy or EnrollmentPolicy()
        self._clock = clock
        self._id_factory = id_factory

    def enroll(self, identity_id: str, samples: Sequence[bytes]) -> EnrollmentResult:
        identity_id = identity_id.strip()
        if not identity_id:
            raise EnrollmentRejected("identity_id_required")
        now = self._clock()
        if self._consent_repository is not None and not self._consent_repository.has_active(
            identity_id, now
        ):
            raise EnrollmentRejected("active_consent_required")
        if len(samples) < self._policy.min_samples:
            raise EnrollmentRejected("insufficient_submitted_samples")
        if len(samples) > self._policy.max_samples:
            raise EnrollmentRejected("too_many_submitted_samples")

        embeddings = []
        original_indices: list[int] = []
        issues: list[SampleIssue] = []

        for index, payload in enumerate(samples):
            try:
                preprocessing = self._preprocessor.process(payload)
            except ValueError:
                issues.append(SampleIssue(index, ("invalid_audio",)))
                continue

            quality_reasons = evaluate_quality(preprocessing.quality, self._policy)
            if quality_reasons:
                issues.append(SampleIssue(index, quality_reasons))
                continue

            try:
                embedding = self._embedder.embed(preprocessing.processed)
            except ModelInferenceError:
                issues.append(SampleIssue(index, ("embedding_failed",)))
                continue
            embeddings.append(embedding)
            original_indices.append(index)

        if len(embeddings) < self._policy.min_samples:
            raise EnrollmentRejected(
                "insufficient_valid_samples",
                sample_issues=tuple(issues),
            )

        try:
            build = build_robust_voice_template(
                embeddings,
                min_samples=self._policy.min_samples,
                outlier_threshold=self._policy.outlier_threshold,
            )
        except ValueError as error:
            raise EnrollmentRejected(
                "inconsistent_speakers",
                sample_issues=tuple(issues),
            ) from error

        issues.extend(
            SampleIssue(original_indices[index], ("inconsistent_voice",))
            for index in build.rejected_indices
        )
        current = self._repository.get_active(identity_id)
        template = VoiceTemplate(
            template_id=self._id_factory(),
            identity_id=identity_id,
            embedding=build.embedding,
            model_id=self._embedder.model_id,
            pipeline_id=self._preprocessor.pipeline_id,
            version=1 if current is None else current.version + 1,
            sample_count=len(build.retained_indices),
            created_at=now,
        )
        self._repository.save(template)
        return EnrollmentResult(template, tuple(sorted(issues, key=lambda item: item.sample_index)))
