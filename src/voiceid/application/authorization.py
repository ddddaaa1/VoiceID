"""Application service for risk-aware voice action authorization."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from voiceid.domain.authorization import (
    ActionAuthorizationPolicy,
    ActionAuthorizationResult,
    ProtectedAction,
    authorize_action,
)

from .verification import VerificationAttempt, VerificationService


@dataclass(frozen=True, slots=True)
class ActionAuthorizationAttempt:
    authorization_id: str
    created_at: datetime
    authorization_policy_id: str
    verification: VerificationAttempt
    result: ActionAuthorizationResult


class ActionAuthorizationService:
    def __init__(
        self,
        verification: VerificationService,
        *,
        policy: ActionAuthorizationPolicy | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self._verification = verification
        self._policy = policy or ActionAuthorizationPolicy()
        self._clock = clock
        self._id_factory = id_factory

    @property
    def policy_id(self) -> str:
        return self._policy.policy_id

    def authorize(
        self,
        identity_id: str,
        action: ProtectedAction,
        payload: bytes,
    ) -> ActionAuthorizationAttempt:
        verification = self._verification.verify(identity_id, payload)
        result = authorize_action(action, verification.result, self._policy)
        return ActionAuthorizationAttempt(
            authorization_id=self._id_factory(),
            created_at=self._clock(),
            authorization_policy_id=self._policy.policy_id,
            verification=verification,
            result=result,
        )
