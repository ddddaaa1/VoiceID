"""Risk-aware authorization rules for voice-initiated device actions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from .models import Decision, VerificationResult


class ProtectedAction(StrEnum):
    PLAY_MEDIA = "play_media"
    PERSONALIZE_ASSISTANT = "personalize_assistant"
    SWITCH_PROFILE = "switch_profile"
    READ_PRIVATE_CONTENT = "read_private_content"
    SEND_MESSAGE = "send_message"
    MAKE_PURCHASE = "make_purchase"
    UNLOCK_PHYSICAL_ACCESS = "unlock_physical_access"


class ActionRisk(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class AuthorizationDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    STEP_UP = "step_up"


DEFAULT_ACTION_RISKS: Mapping[ProtectedAction, ActionRisk] = MappingProxyType(
    {
        ProtectedAction.PLAY_MEDIA: ActionRisk.LOW,
        ProtectedAction.PERSONALIZE_ASSISTANT: ActionRisk.LOW,
        ProtectedAction.SWITCH_PROFILE: ActionRisk.MODERATE,
        ProtectedAction.READ_PRIVATE_CONTENT: ActionRisk.MODERATE,
        ProtectedAction.SEND_MESSAGE: ActionRisk.HIGH,
        ProtectedAction.MAKE_PURCHASE: ActionRisk.HIGH,
        ProtectedAction.UNLOCK_PHYSICAL_ACCESS: ActionRisk.HIGH,
    }
)


@dataclass(frozen=True, slots=True)
class ActionAuthorizationPolicy:
    """Versioned product policy; clients cannot choose their own risk tier."""

    policy_id: str = "wearable-action-risk-v1"

    def __post_init__(self) -> None:
        if not self.policy_id:
            raise ValueError("policy_id is required")

    def risk_for(self, action: ProtectedAction) -> ActionRisk:
        return DEFAULT_ACTION_RISKS[action]


@dataclass(frozen=True, slots=True)
class ActionAuthorizationResult:
    action: ProtectedAction
    risk: ActionRisk
    decision: AuthorizationDecision
    reasons: tuple[str, ...]


def authorize_action(
    action: ProtectedAction,
    verification: VerificationResult,
    policy: ActionAuthorizationPolicy | None = None,
) -> ActionAuthorizationResult:
    """Convert biometric evidence into a safe action-level decision.

    Voice alone never authorizes high-risk actions. Moderate-risk actions also
    require an accepted anti-spoofing result; otherwise the caller must use a
    device biometric or passkey.
    """

    active_policy = policy or ActionAuthorizationPolicy()
    risk = active_policy.risk_for(action)

    if verification.decision is Decision.REJECT:
        return ActionAuthorizationResult(
            action, risk, AuthorizationDecision.DENY, ("voice_verification_rejected",)
        )

    if verification.decision is Decision.REVIEW:
        return ActionAuthorizationResult(
            action,
            risk,
            AuthorizationDecision.STEP_UP,
            ("voice_verification_inconclusive", "device_authentication_required"),
        )

    if risk is ActionRisk.HIGH:
        return ActionAuthorizationResult(
            action,
            risk,
            AuthorizationDecision.STEP_UP,
            ("high_risk_action", "device_authentication_required"),
        )

    if risk is ActionRisk.MODERATE and verification.spoof_probability is None:
        return ActionAuthorizationResult(
            action,
            risk,
            AuthorizationDecision.STEP_UP,
            ("spoof_evidence_required", "device_authentication_required"),
        )

    return ActionAuthorizationResult(
        action,
        risk,
        AuthorizationDecision.ALLOW,
        ("voice_assurance_sufficient",),
    )
