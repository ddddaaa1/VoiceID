"""Generate scored trials through the real enrollment and verification services."""

from __future__ import annotations

from voiceid.application.enrollment import EnrollmentRejected, EnrollmentService
from voiceid.application.verification import VerificationService, VerificationUnavailable
from voiceid.domain.evaluation import (
    AudioFileReference,
    AudioTrialManifest,
    ScoredTrial,
    ScoredTrialManifest,
)
from voiceid.ports.evaluation import AudioAssetReader, AudioAssetUnavailable


class TrialScoringError(RuntimeError):
    def __init__(self, code: str, item_id: str) -> None:
        super().__init__(f"{code}: {item_id}")
        self.code = code
        self.item_id = item_id


class AudioTrialScorer:
    def __init__(
        self,
        enrollment_service: EnrollmentService,
        verification_service: VerificationService,
        audio_reader: AudioAssetReader,
    ) -> None:
        self._enrollment_service = enrollment_service
        self._verification_service = verification_service
        self._audio_reader = audio_reader

    def score(self, manifest: AudioTrialManifest) -> ScoredTrialManifest:
        model_id: str | None = None
        pipeline_id: str | None = None

        for enrollment in manifest.enrollments:
            payloads = [
                self._read(reference, enrollment.identity_id)
                for reference in enrollment.samples
            ]
            try:
                result = self._enrollment_service.enroll(enrollment.identity_id, payloads)
            except EnrollmentRejected as error:
                raise TrialScoringError(
                    f"enrollment_{error.code}", enrollment.identity_id
                ) from error
            template = result.template
            if model_id is None:
                model_id = template.model_id
                pipeline_id = template.pipeline_id
            elif (template.model_id, template.pipeline_id) != (model_id, pipeline_id):
                raise TrialScoringError("inconsistent_system_version", enrollment.identity_id)

        scored_trials: list[ScoredTrial] = []
        for trial in manifest.trials:
            payload = self._read(trial.sample, trial.trial_id)
            try:
                attempt = self._verification_service.verify(
                    trial.claimed_identity_id, payload
                )
            except VerificationUnavailable as error:
                raise TrialScoringError(
                    f"verification_{error.code}", trial.trial_id
                ) from error
            if attempt.result.speaker_score is None:
                reasons = "_and_".join(attempt.result.reasons) or "unknown"
                raise TrialScoringError(f"score_unavailable_{reasons}", trial.trial_id)
            if (attempt.model_id, attempt.pipeline_id) != (model_id, pipeline_id):
                raise TrialScoringError("inconsistent_system_version", trial.trial_id)
            scored_trials.append(
                ScoredTrial(
                    trial_id=trial.trial_id,
                    partition=trial.partition,
                    label=trial.label,
                    enrollment_speaker_id=self._speaker_for_identity(
                        manifest, trial.claimed_identity_id
                    ),
                    probe_speaker_id=trial.probe_speaker_id,
                    score=attempt.result.speaker_score,
                    condition=trial.condition,
                )
            )

        if model_id is None or pipeline_id is None:
            raise TrialScoringError("system_version_unavailable", manifest.dataset_id)
        return ScoredTrialManifest(
            dataset_id=manifest.dataset_id,
            dataset_version=manifest.dataset_version,
            model_id=model_id,
            pipeline_id=pipeline_id,
            trials=tuple(scored_trials),
        )

    def _read(self, reference: AudioFileReference, item_id: str) -> bytes:
        try:
            return self._audio_reader.read(reference)
        except AudioAssetUnavailable as error:
            raise TrialScoringError(f"audio_{error.code}", item_id) from error

    @staticmethod
    def _speaker_for_identity(manifest: AudioTrialManifest, identity_id: str) -> str:
        return next(
            enrollment.speaker_id
            for enrollment in manifest.enrollments
            if enrollment.identity_id == identity_id
        )
