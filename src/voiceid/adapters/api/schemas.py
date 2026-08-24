"""Public versioned API response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from voiceid.application.enrollment import EnrollmentResult
from voiceid.application.verification import VerificationAttempt
from voiceid.domain.models import Decision


class StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictResponse):
    status: str
    api_version: str
    persistence: str
    speaker_model_id: str
    spoof_model_id: str | None
    verification_policy_id: str
    anti_spoofing_enabled: bool


class SampleIssueResponse(StrictResponse):
    sample_index: int
    reasons: list[str]


class EnrollmentResponse(StrictResponse):
    template_id: str
    identity_id: str
    template_version: int
    retained_samples: int
    discarded_samples: list[SampleIssueResponse]
    model_id: str
    pipeline_id: str
    created_at: datetime

    @classmethod
    def from_result(cls, result: EnrollmentResult) -> EnrollmentResponse:
        template = result.template
        return cls(
            template_id=template.template_id,
            identity_id=template.identity_id,
            template_version=template.version,
            retained_samples=template.sample_count,
            discarded_samples=[
                SampleIssueResponse(
                    sample_index=issue.sample_index,
                    reasons=list(issue.reasons),
                )
                for issue in result.discarded_samples
            ],
            model_id=template.model_id,
            pipeline_id=template.pipeline_id,
            created_at=template.created_at,
        )


class VerificationResponse(StrictResponse):
    attempt_id: str
    created_at: datetime
    identity_id: str
    template_id: str
    template_version: int
    model_id: str
    spoof_model_id: str | None
    pipeline_id: str
    policy_id: str
    decision: Decision
    speaker_score: float | None
    spoof_probability: float | None
    reasons: list[str]

    @classmethod
    def from_attempt(cls, attempt: VerificationAttempt) -> VerificationResponse:
        return cls(
            attempt_id=attempt.attempt_id,
            created_at=attempt.created_at,
            identity_id=attempt.identity_id,
            template_id=attempt.template_id,
            template_version=attempt.template_version,
            model_id=attempt.model_id,
            spoof_model_id=attempt.spoof_model_id,
            pipeline_id=attempt.pipeline_id,
            policy_id=attempt.policy_id,
            decision=attempt.result.decision,
            speaker_score=attempt.result.speaker_score,
            spoof_probability=attempt.result.spoof_probability,
            reasons=list(attempt.result.reasons),
        )


class ErrorDetail(StrictResponse):
    code: str
    message: str
    details: object | None = None


class ErrorResponse(StrictResponse):
    error: ErrorDetail
