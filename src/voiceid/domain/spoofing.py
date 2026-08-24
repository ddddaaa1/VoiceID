"""Versioned anti-spoofing score protocol values."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from voiceid.domain.evaluation import TrialPartition

SPOOF_SCORE_SCHEMA_VERSION = "voiceid-spoof-scores/v1"


class SpoofProtocolError(ValueError):
    """Raised when countermeasure scores violate the evaluation protocol."""


class SpoofLabel(StrEnum):
    BONAFIDE = "bonafide"
    SPOOF = "spoof"


class AttackCategory(StrEnum):
    BONAFIDE = "bonafide"
    REPLAY = "replay"
    SYNTHETIC = "synthetic"
    VOICE_CONVERSION = "voice_conversion"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SpoofScoreTrial:
    trial_id: str
    partition: TrialPartition
    speaker_id: str
    label: SpoofLabel
    attack_category: AttackCategory
    attack_id: str
    spoof_probability: float
    condition: str = "unspecified"

    def __post_init__(self) -> None:
        if not isinstance(self.partition, TrialPartition):
            raise SpoofProtocolError("spoof trial partition is invalid")
        if not isinstance(self.label, SpoofLabel):
            raise SpoofProtocolError("spoof trial label is invalid")
        if not isinstance(self.attack_category, AttackCategory):
            raise SpoofProtocolError("attack category is invalid")
        required = (self.trial_id, self.speaker_id, self.attack_id, self.condition)
        if any(
            not isinstance(value, str) or not value or value != value.strip() for value in required
        ):
            raise SpoofProtocolError("spoof trial identifiers must be non-empty")
        if (
            not isinstance(self.spoof_probability, (int, float))
            or isinstance(self.spoof_probability, bool)
            or not math.isfinite(self.spoof_probability)
            or not 0.0 <= self.spoof_probability <= 1.0
        ):
            raise SpoofProtocolError("spoof probability must be finite and between 0 and 1")
        if self.label is SpoofLabel.BONAFIDE:
            if self.attack_category is not AttackCategory.BONAFIDE:
                raise SpoofProtocolError("bonafide trials require the bonafide category")
            if self.attack_id != "bonafide":
                raise SpoofProtocolError("bonafide trials require attack_id 'bonafide'")
        elif self.attack_category is AttackCategory.BONAFIDE:
            raise SpoofProtocolError("spoof trials cannot use the bonafide category")


@dataclass(frozen=True, slots=True)
class SpoofScoreManifest:
    dataset_id: str
    dataset_version: str
    countermeasure_model_id: str
    pipeline_id: str
    trials: tuple[SpoofScoreTrial, ...]
    schema_version: str = SPOOF_SCORE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SPOOF_SCORE_SCHEMA_VERSION:
            raise SpoofProtocolError(f"unsupported schema version: {self.schema_version!r}")
        metadata = (
            self.dataset_id,
            self.dataset_version,
            self.countermeasure_model_id,
            self.pipeline_id,
        )
        if any(
            not isinstance(value, str) or not value or value != value.strip() for value in metadata
        ):
            raise SpoofProtocolError("spoof manifest metadata must be non-empty")
        if not self.trials:
            raise SpoofProtocolError("spoof manifest must contain trials")
        trial_ids = [trial.trial_id for trial in self.trials]
        if len(trial_ids) != len(set(trial_ids)):
            raise SpoofProtocolError("spoof trial identifiers must be unique")

        speakers_by_partition: dict[TrialPartition, set[str]] = {}
        for partition in TrialPartition:
            partition_trials = self.trials_for(partition)
            labels = {trial.label for trial in partition_trials}
            if labels != set(SpoofLabel):
                raise SpoofProtocolError(f"{partition.value} requires bonafide and spoof trials")
            speakers_by_partition[partition] = {trial.speaker_id for trial in partition_trials}

        overlap = set.intersection(*speakers_by_partition.values())
        if overlap:
            raise SpoofProtocolError(
                "speaker leakage between development and evaluation: " + ", ".join(sorted(overlap))
            )

    def trials_for(self, partition: TrialPartition) -> tuple[SpoofScoreTrial, ...]:
        return tuple(trial for trial in self.trials if trial.partition is partition)
