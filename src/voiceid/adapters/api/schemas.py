"""Public versioned API response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from voiceid.application.authorization import ActionAuthorizationAttempt
from voiceid.application.enrollment import EnrollmentResult
from voiceid.application.grants import AuthorizationGrantIssue
from voiceid.application.verification import VerificationAttempt
from voiceid.domain.authorization import ActionRisk, AuthorizationDecision, ProtectedAction
from voiceid.domain.governance import ConsentGrant, RevocationResult
from voiceid.domain.grants import ConsumedAuthorizationGrant
from voiceid.domain.models import Decision


class StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictResponse):
    status: str
    api_version: str
    persistence: str
    speaker_model_id: str
    spoof_model_id: str | None
    verification_policy_id: str
    anti_spoofing_enabled: bool
    authorization_policy_id: str
    authorization_grants_enabled: bool


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


class ActionAuthorizationResponse(StrictResponse):
    authorization_id: str
    created_at: datetime
    identity_id: str
    action: ProtectedAction
    risk: ActionRisk
    decision: AuthorizationDecision
    authorization_policy_id: str
    reasons: list[str]
    verification: VerificationResponse

    @classmethod
    def from_attempt(cls, attempt: ActionAuthorizationAttempt) -> ActionAuthorizationResponse:
        return cls(
            authorization_id=attempt.authorization_id,
            created_at=attempt.created_at,
            identity_id=attempt.verification.identity_id,
            action=attempt.result.action,
            risk=attempt.result.risk,
            decision=attempt.result.decision,
            authorization_policy_id=attempt.authorization_policy_id,
            reasons=list(attempt.result.reasons),
            verification=VerificationResponse.from_attempt(attempt.verification),
        )


class AuthorizationGrantResponse(StrictResponse):
    grant_id: str
    authorization_id: str
    identity_id: str
    device_id: str
    action: ProtectedAction
    issued_at: datetime
    expires_at: datetime
    token: str


class AuthorizationGrantIssueResponse(StrictResponse):
    authorization: ActionAuthorizationResponse
    grant: AuthorizationGrantResponse | None

    @classmethod
    def from_issue(cls, issue: AuthorizationGrantIssue) -> AuthorizationGrantIssueResponse:
        grant_response = None
        if issue.grant is not None and issue.token is not None:
            grant_response = AuthorizationGrantResponse(
                grant_id=issue.grant.grant_id,
                authorization_id=issue.grant.authorization_id,
                identity_id=issue.grant.identity_id,
                device_id=issue.grant.device_id,
                action=issue.grant.action,
                issued_at=issue.grant.issued_at,
                expires_at=issue.grant.expires_at,
                token=issue.token,
            )
        return cls(
            authorization=ActionAuthorizationResponse.from_attempt(issue.authorization),
            grant=grant_response,
        )


class GrantConsumptionRequest(StrictRequest):
    token: str = Field(min_length=1, max_length=4096)
    action: ProtectedAction


class GrantConsumptionResponse(StrictResponse):
    grant_id: str
    authorization_id: str
    identity_id: str
    device_id: str
    action: ProtectedAction
    consumed_at: datetime

    @classmethod
    def from_result(cls, result: ConsumedAuthorizationGrant) -> GrantConsumptionResponse:
        return cls(**{field: getattr(result, field) for field in cls.model_fields})


class ConsentRequest(StrictRequest):
    purpose: str = Field(min_length=1, max_length=200)
    notice_version: str = Field(min_length=1, max_length=100)
    expires_at: datetime


class ConsentResponse(StrictResponse):
    consent_id: str
    identity_id: str
    purpose: str
    notice_version: str
    granted_at: datetime
    expires_at: datetime

    @classmethod
    def from_grant(cls, grant: ConsentGrant) -> ConsentResponse:
        return cls(**{field: getattr(grant, field) for field in cls.model_fields})


class RevocationResponse(StrictResponse):
    identity_id: str
    revoked_templates: int
    revoked_consents: int
    revoked_at: datetime

    @classmethod
    def from_result(cls, result: RevocationResult) -> RevocationResponse:
        return cls(**{field: getattr(result, field) for field in cls.model_fields})


class ErrorDetail(StrictResponse):
    code: str
    message: str
    details: object | None = None


class ErrorResponse(StrictResponse):
    error: ErrorDetail
