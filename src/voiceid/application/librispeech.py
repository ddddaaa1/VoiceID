"""Deterministic LibriSpeech speaker and recording selection rules."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from voiceid.domain.evaluation import TrialPartition


class CorpusPreparationError(ValueError):
    """Raised when a source corpus cannot satisfy the evaluation protocol."""


@dataclass(frozen=True, slots=True)
class LibriSpeechClip:
    source_path: Path
    speaker_id: str
    utterance_id: str
    duration_seconds: float

    def __post_init__(self) -> None:
        if not self.speaker_id or not self.utterance_id:
            raise CorpusPreparationError("clip identifiers must be non-empty")
        if self.duration_seconds <= 0:
            raise CorpusPreparationError("clip duration must be positive")


@dataclass(frozen=True, slots=True)
class LibriSpeechImportConfig:
    speakers_per_partition: int = 10
    enrollment_clips_per_speaker: int = 3
    probe_clips_per_speaker: int = 3
    minimum_duration_seconds: float = 2.5
    maximum_duration_seconds: float = 12.0
    selection_seed: str = "voiceid-librispeech-v1"

    def __post_init__(self) -> None:
        if self.speakers_per_partition < 2:
            raise CorpusPreparationError("at least two speakers per partition are required")
        if not 3 <= self.enrollment_clips_per_speaker <= 8:
            raise CorpusPreparationError("enrollment requires three to eight clips")
        if self.probe_clips_per_speaker <= 0:
            raise CorpusPreparationError("at least one probe clip is required")
        if (
            self.minimum_duration_seconds <= 0
            or self.maximum_duration_seconds < self.minimum_duration_seconds
        ):
            raise CorpusPreparationError("duration limits are invalid")
        if not self.selection_seed or self.selection_seed != self.selection_seed.strip():
            raise CorpusPreparationError("selection seed must be non-empty and trimmed")

    @property
    def clips_per_speaker(self) -> int:
        return self.enrollment_clips_per_speaker + self.probe_clips_per_speaker


@dataclass(frozen=True, slots=True)
class SelectedSpeaker:
    speaker_id: str
    partition: TrialPartition
    enrollment_clips: tuple[LibriSpeechClip, ...]
    probe_clips: tuple[LibriSpeechClip, ...]


def select_librispeech_clips(
    development_clips: tuple[LibriSpeechClip, ...],
    evaluation_clips: tuple[LibriSpeechClip, ...],
    config: LibriSpeechImportConfig,
) -> tuple[SelectedSpeaker, ...]:
    """Select a stable, speaker-disjoint cohort without filesystem-order dependence."""

    development_speakers = {clip.speaker_id for clip in development_clips}
    evaluation_speakers = {clip.speaker_id for clip in evaluation_clips}
    overlap = development_speakers & evaluation_speakers
    if overlap:
        raise CorpusPreparationError(
            "source partitions share speakers: " + ", ".join(sorted(overlap))
        )

    selected = _select_partition(
        development_clips, TrialPartition.DEVELOPMENT, config
    ) + _select_partition(evaluation_clips, TrialPartition.EVALUATION, config)
    return tuple(selected)


def _select_partition(
    clips: tuple[LibriSpeechClip, ...],
    partition: TrialPartition,
    config: LibriSpeechImportConfig,
) -> list[SelectedSpeaker]:
    eligible: dict[str, list[LibriSpeechClip]] = defaultdict(list)
    for clip in clips:
        if (
            config.minimum_duration_seconds
            <= clip.duration_seconds
            <= config.maximum_duration_seconds
        ):
            eligible[clip.speaker_id].append(clip)

    eligible = {
        speaker_id: speaker_clips
        for speaker_id, speaker_clips in eligible.items()
        if len(speaker_clips) >= config.clips_per_speaker
    }
    if len(eligible) < config.speakers_per_partition:
        raise CorpusPreparationError(
            f"{partition.value} has {len(eligible)} eligible speakers; "
            f"{config.speakers_per_partition} required"
        )

    ordered_speakers = sorted(
        eligible,
        key=lambda speaker_id: _stable_key(
            config.selection_seed, partition.value, "speaker", speaker_id
        ),
    )[: config.speakers_per_partition]

    selections = []
    for speaker_id in ordered_speakers:
        ordered_clips = sorted(
            eligible[speaker_id],
            key=lambda clip: _stable_key(
                config.selection_seed,
                partition.value,
                speaker_id,
                clip.utterance_id,
            ),
        )[: config.clips_per_speaker]
        split = config.enrollment_clips_per_speaker
        selections.append(
            SelectedSpeaker(
                speaker_id=speaker_id,
                partition=partition,
                enrollment_clips=tuple(ordered_clips[:split]),
                probe_clips=tuple(ordered_clips[split:]),
            )
        )
    return selections


def _stable_key(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()
