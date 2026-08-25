from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from voiceid.application.authorization import ActionAuthorizationService
from voiceid.application.verification import VerificationAttempt
from voiceid.domain.authorization import (
    ActionAuthorizationPolicy,
    ActionRisk,
    AuthorizationDecision,
    ProtectedAction,
    authorize_action,
)
from voiceid.domain.models import Decision, VerificationResult

CREATED_AT = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


def verification_result(
    decision: Decision,
    *,
    spoof_probability: float | None = None,
) -> VerificationResult:
    return VerificationResult(decision, 0.91, spoof_probability, ("test_evidence",))


class ActionAuthorizationPolicyTests(unittest.TestCase):
    def test_low_risk_action_allows_an_accepted_voice_match(self) -> None:
        result = authorize_action(
            ProtectedAction.PLAY_MEDIA,
            verification_result(Decision.ACCEPT),
        )

        self.assertEqual(result.risk, ActionRisk.LOW)
        self.assertEqual(result.decision, AuthorizationDecision.ALLOW)
        self.assertEqual(result.reasons, ("voice_assurance_sufficient",))

    def test_moderate_action_steps_up_without_spoof_evidence(self) -> None:
        result = authorize_action(
            ProtectedAction.READ_PRIVATE_CONTENT,
            verification_result(Decision.ACCEPT),
        )

        self.assertEqual(result.risk, ActionRisk.MODERATE)
        self.assertEqual(result.decision, AuthorizationDecision.STEP_UP)
        self.assertIn("spoof_evidence_required", result.reasons)

    def test_moderate_action_allows_accepted_voice_and_spoof_evidence(self) -> None:
        result = authorize_action(
            ProtectedAction.SWITCH_PROFILE,
            verification_result(Decision.ACCEPT, spoof_probability=0.04),
        )

        self.assertEqual(result.decision, AuthorizationDecision.ALLOW)

    def test_high_risk_action_always_requires_a_stronger_factor(self) -> None:
        result = authorize_action(
            ProtectedAction.MAKE_PURCHASE,
            verification_result(Decision.ACCEPT, spoof_probability=0.01),
        )

        self.assertEqual(result.risk, ActionRisk.HIGH)
        self.assertEqual(result.decision, AuthorizationDecision.STEP_UP)
        self.assertIn("high_risk_action", result.reasons)

    def test_rejected_voice_denies_every_action(self) -> None:
        result = authorize_action(
            ProtectedAction.PLAY_MEDIA,
            verification_result(Decision.REJECT),
        )

        self.assertEqual(result.decision, AuthorizationDecision.DENY)

    def test_inconclusive_voice_requires_step_up_instead_of_denial(self) -> None:
        result = authorize_action(
            ProtectedAction.PLAY_MEDIA,
            verification_result(Decision.REVIEW),
        )

        self.assertEqual(result.decision, AuthorizationDecision.STEP_UP)


class StubVerificationService:
    def __init__(self) -> None:
        self.received: tuple[str, bytes] | None = None

    def verify(self, identity_id: str, payload: bytes) -> VerificationAttempt:
        self.received = identity_id, payload
        return VerificationAttempt(
            attempt_id="verification-1",
            created_at=CREATED_AT,
            identity_id=identity_id,
            template_id="template-1",
            template_version=1,
            model_id="speaker-model-v1",
            spoof_model_id=None,
            pipeline_id="audio-v1",
            policy_id="speaker-policy-v1",
            result=verification_result(Decision.ACCEPT),
        )


class ActionAuthorizationServiceTests(unittest.TestCase):
    def test_service_preserves_verification_evidence_and_policy_lineage(self) -> None:
        verification = StubVerificationService()
        service = ActionAuthorizationService(
            verification,  # type: ignore[arg-type]
            policy=ActionAuthorizationPolicy("test-action-policy-v2"),
            clock=lambda: CREATED_AT,
            id_factory=lambda: "authorization-1",
        )

        attempt = service.authorize("owner-1", ProtectedAction.SEND_MESSAGE, b"wave")

        self.assertEqual(verification.received, ("owner-1", b"wave"))
        self.assertEqual(attempt.authorization_id, "authorization-1")
        self.assertEqual(attempt.authorization_policy_id, "test-action-policy-v2")
        self.assertEqual(attempt.verification.attempt_id, "verification-1")
        self.assertEqual(attempt.result.decision, AuthorizationDecision.STEP_UP)


if __name__ == "__main__":
    unittest.main()
