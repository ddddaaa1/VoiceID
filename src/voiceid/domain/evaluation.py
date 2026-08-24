"""Versioned, leakage-resistant speaker-verification trial values."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

SCORED_TRIAL_SCHEMA_VERSION = "voiceid-scored-trials/v1"
AUDIO_TRIAL_SCHEMA_VERSION = "voiceid-audio-trials/v1"


class EvaluationProtocolError(ValueError):
    """Raised when a trial manifest violates the evaluation protocol."""


class TrialPartition(StrEnum):
    DEVELOPMENT = "development"
    EVALUATION = "evaluation"


class TrialLabel(StrEnum):
    GENUINE = "genuine"
    IMPOSTOR = "impostor"


@dataclass(frozen=True, slots=True)
class AudioFileReference:
    path: str
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path or self.path != self.path.strip():
            raise EvaluationProtocolError("audio path must be a non-empty relative path")
        parsed = PurePosixPath(self.path)
        if (
            parsed.is_absolute()
            or ".." in parsed.parts
            or "\\" in self.path
            or parsed.suffix.lower() != ".wav"
            or parsed.as_posix() != self.path
        ):
            raise EvaluationProtocolError("audio path must be a safe relative PCM WAVE path")
        if not isinstance(self.sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.sha256
        ):
            raise EvaluationProtocolError("audio sha256 must be 64 lowercase hex characters")


@dataclass(frozen=True, slots=True)
class AudioEnrollment:
    identity_id: str
    speaker_id: str
    partition: TrialPartition
    samples: tuple[AudioFileReference, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.partition, TrialPartition):
            raise EvaluationProtocolError("enrollment partition is invalid")
        if any(
            not isinstance(value, str) or not value or value != value.strip()
            for value in (self.identity_id, self.speaker_id)
        ):
            raise EvaluationProtocolError("enrollment identifiers must be non-empty")
        if not 3 <= len(self.samples) <= 8:
            raise EvaluationProtocolError("enrollment requires three to eight samples")
        hashes = [sample.sha256 for sample in self.samples]
        if len(hashes) != len(set(hashes)):
            raise EvaluationProtocolError("enrollment samples must contain unique audio")


@dataclass(frozen=True, slots=True)
class AudioTrial:
    trial_id: str
    partition: TrialPartition
    label: TrialLabel
    claimed_identity_id: str
    probe_speaker_id: str
    sample: AudioFileReference
    condition: str = "unspecified"

    def __post_init__(self) -> None:
        if not isinstance(self.partition, TrialPartition):
            raise EvaluationProtocolError("audio trial partition is invalid")
        if not isinstance(self.label, TrialLabel):
            raise EvaluationProtocolError("audio trial label is invalid")
        required = (
            self.trial_id,
            self.claimed_identity_id,
            self.probe_speaker_id,
            self.condition,
        )
        if any(
            not isinstance(value, str) or not value or value != value.strip()
            for value in required
        ):
            raise EvaluationProtocolError("audio trial identifiers must be non-empty")


@dataclass(frozen=True, slots=True)
class AudioTrialManifest:
    dataset_id: str
    dataset_version: str
    consent_attestation: str
    enrollments: tuple[AudioEnrollment, ...]
    trials: tuple[AudioTrial, ...]
    schema_version: str = AUDIO_TRIAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != AUDIO_TRIAL_SCHEMA_VERSION:
            raise EvaluationProtocolError(
                f"unsupported schema version: {self.schema_version!r}"
            )
        metadata = (self.dataset_id, self.dataset_version, self.consent_attestation)
        if any(
            not isinstance(value, str) or not value or value != value.strip()
            for value in metadata
        ):
            raise EvaluationProtocolError("audio manifest metadata must be non-empty")
        if not self.enrollments or not self.trials:
            raise EvaluationProtocolError("audio manifest requires enrollments and trials")

        identities = [enrollment.identity_id for enrollment in self.enrollments]
        if len(identities) != len(set(identities)):
            raise EvaluationProtocolError("enrollment identity identifiers must be unique")
        trial_ids = [trial.trial_id for trial in self.trials]
        if len(trial_ids) != len(set(trial_ids)):
            raise EvaluationProtocolError("trial identifiers must be unique")
        enrollment_by_identity = {
            enrollment.identity_id: enrollment for enrollment in self.enrollments
        }

        speakers_by_partition: dict[TrialPartition, set[str]] = {
            partition: {
                enrollment.speaker_id
                for enrollment in self.enrollments
                if enrollment.partition is partition
            }
            for partition in TrialPartition
        }
        labels_by_partition: dict[TrialPartition, set[TrialLabel]] = {
            partition: set() for partition in TrialPartition
        }
        digests_by_partition: dict[TrialPartition, set[str]] = {
            partition: {
                sample.sha256
                for enrollment in self.enrollments
                if enrollment.partition is partition
                for sample in enrollment.samples
            }
            for partition in TrialPartition
        }

        for trial in self.trials:
            enrollment = enrollment_by_identity.get(trial.claimed_identity_id)
            if enrollment is None:
                raise EvaluationProtocolError(
                    f"trial {trial.trial_id!r} references an unknown claimed identity"
                )
            if enrollment.partition is not trial.partition:
                raise EvaluationProtocolError(
                    f"trial {trial.trial_id!r} crosses evaluation partitions"
                )
            expected_label = (
                TrialLabel.GENUINE
                if enrollment.speaker_id == trial.probe_speaker_id
                else TrialLabel.IMPOSTOR
            )
            if trial.label is not expected_label:
                raise EvaluationProtocolError(
                    f"trial {trial.trial_id!r} label conflicts with its speaker identifiers"
                )
            speakers_by_partition[trial.partition].add(trial.probe_speaker_id)
            labels_by_partition[trial.partition].add(trial.label)
            digests_by_partition[trial.partition].add(trial.sample.sha256)

        for partition, labels in labels_by_partition.items():
            if labels != set(TrialLabel):
                raise EvaluationProtocolError(
                    f"{partition.value} requires genuine and impostor trials"
                )
        leaked_speakers = set.intersection(*speakers_by_partition.values())
        if leaked_speakers:
            leaked = ", ".join(sorted(leaked_speakers))
            raise EvaluationProtocolError(
                f"speaker leakage between development and evaluation: {leaked}"
            )
        leaked_audio = set.intersection(*digests_by_partition.values())
        if leaked_audio:
            raise EvaluationProtocolError(
                "audio content leakage between development and evaluation"
            )
        enrollment_hashes = {
            sample.sha256
            for enrollment in self.enrollments
            for sample in enrollment.samples
        }
        probe_hashes = {trial.sample.sha256 for trial in self.trials}
        if enrollment_hashes & probe_hashes:
            raise EvaluationProtocolError("enrollment audio cannot be reused as probe audio")
        _reject_conflicting_audio_owners(
            (
                (sample.sha256, enrollment.speaker_id)
                for enrollment in self.enrollments
                for sample in enrollment.samples
            ),
            "enrollment",
        )
        _reject_conflicting_audio_owners(
            ((trial.sample.sha256, trial.probe_speaker_id) for trial in self.trials),
            "probe",
        )


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


def _reject_conflicting_audio_owners(
    digest_owners: Iterable[tuple[str, str]], asset_type: str
) -> None:
    owners: dict[str, str] = {}
    for digest, speaker_id in digest_owners:
        previous = owners.setdefault(digest, speaker_id)
        if previous != speaker_id:
            raise EvaluationProtocolError(
                f"{asset_type} audio cannot represent multiple speakers"
            )
