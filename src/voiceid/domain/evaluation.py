"""Versioned, leakage-resistant speaker-verification trial values."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

SCORED_TRIAL_SCHEMA_VERSION = "voiceid-scored-trials/v1"


class EvaluationProtocolError(ValueError):
    """Raised when a trial manifest violates the evaluation protocol."""


class TrialPartition(StrEnum):
    DEVELOPMENT = "development"
    EVALUATION = "evaluation"


class TrialLabel(StrEnum):
    GENUINE = "genuine"
    IMPOSTOR = "impostor"


@dataclass(frozen=True, slots=True)
class ScoredTrial:
    trial_id: str
    partition: TrialPartition
    label: TrialLabel
    enrollment_speaker_id: str
    probe_speaker_id: str
    score: float
    condition: str = "unspecified"

    def __post_init__(self) -> None:
        if not isinstance(self.partition, TrialPartition):
            raise EvaluationProtocolError("trial partition is invalid")
        if not isinstance(self.label, TrialLabel):
            raise EvaluationProtocolError("trial label is invalid")
        required = (
            self.trial_id,
            self.enrollment_speaker_id,
            self.probe_speaker_id,
            self.condition,
        )
        if any(
            not isinstance(value, str) or not value or value != value.strip()
            for value in required
        ):
            raise EvaluationProtocolError("trial identifiers and condition must be non-empty")
        if (
            not isinstance(self.score, (int, float))
            or isinstance(self.score, bool)
            or not math.isfinite(self.score)
            or not -1.0 <= self.score <= 1.0
        ):
            raise EvaluationProtocolError("trial score must be finite and between -1 and 1")
        expected_label = (
            TrialLabel.GENUINE
            if self.enrollment_speaker_id == self.probe_speaker_id
            else TrialLabel.IMPOSTOR
        )
        if self.label is not expected_label:
            raise EvaluationProtocolError(
                f"trial {self.trial_id!r} label conflicts with its speaker identifiers"
            )


@dataclass(frozen=True, slots=True)
class ScoredTrialManifest:
    dataset_id: str
    dataset_version: str
    model_id: str
    pipeline_id: str
    trials: tuple[ScoredTrial, ...]
    schema_version: str = SCORED_TRIAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCORED_TRIAL_SCHEMA_VERSION:
            raise EvaluationProtocolError(
                f"unsupported schema version: {self.schema_version!r}"
            )
        metadata = (self.dataset_id, self.dataset_version, self.model_id, self.pipeline_id)
        if any(
            not isinstance(value, str) or not value or value != value.strip()
            for value in metadata
        ):
            raise EvaluationProtocolError("manifest metadata must be non-empty")
        if not self.trials:
            raise EvaluationProtocolError("manifest must contain trials")
        trial_ids = [trial.trial_id for trial in self.trials]
        if len(trial_ids) != len(set(trial_ids)):
            raise EvaluationProtocolError("trial identifiers must be unique")

        speakers_by_partition: dict[TrialPartition, set[str]] = {}
        for partition in TrialPartition:
            partition_trials = self.trials_for(partition)
            labels = {trial.label for trial in partition_trials}
            if labels != set(TrialLabel):
                raise EvaluationProtocolError(
                    f"{partition.value} requires genuine and impostor trials"
                )
            speakers_by_partition[partition] = {
                speaker
                for trial in partition_trials
                for speaker in (trial.enrollment_speaker_id, trial.probe_speaker_id)
            }

        leaked_speakers = set.intersection(*speakers_by_partition.values())
        if leaked_speakers:
            leaked = ", ".join(sorted(leaked_speakers))
            raise EvaluationProtocolError(
                f"speaker leakage between development and evaluation: {leaked}"
            )

    def trials_for(self, partition: TrialPartition) -> tuple[ScoredTrial, ...]:
        return tuple(trial for trial in self.trials if trial.partition is partition)
