"""Batch and resume-friendly ASVspoof 2019 AASIST scoring workflow."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from voiceid.adapters.evaluation.asvspoof2019_audio import (
    Asvspoof2019LaTrial,
    DecodedCorpusAudio,
)
from voiceid.adapters.models.aasist import AasistModelScore
from voiceid.domain.audio import AudioBuffer
from voiceid.domain.evaluation import TrialPartition
from voiceid.domain.spoofing import SpoofLabel


class CorpusAudioReader(Protocol):
    def read(self, path: Path) -> DecodedCorpusAudio:
        """Read one bounded corpus asset."""


class BatchAasistScorer(Protocol):
    @property
    def model_id(self) -> str:
        """Return the immutable countermeasure model ID."""

    def score_batch(self, audio: Sequence[AudioBuffer]) -> tuple[AasistModelScore, ...]:
        """Score one inference batch."""


@dataclass(frozen=True, slots=True)
class Asvspoof2019ScoreRecord:
    sequence: int
    trial_id: str
    speaker_id: str
    partition: TrialPartition
    label: SpoofLabel
    attack_id: str
    audio_relative_path: str
    audio_sha256: str
    audio_bytes: int
    spoof_logit: float
    bonafide_logit: float
    spoof_probability: float


def score_asvspoof2019_trials(
    trials: Sequence[Asvspoof2019LaTrial],
    scorer: BatchAasistScorer,
    reader: CorpusAudioReader,
    *,
    corpus_root: Path,
    start_sequence: int = 0,
    batch_size: int = 16,
    on_batch: Callable[[tuple[Asvspoof2019ScoreRecord, ...]], None] | None = None,
) -> Iterator[Asvspoof2019ScoreRecord]:
    """Score an ordered suffix and persist each completed batch through a callback."""

    if batch_size <= 0:
        raise ValueError("AASIST scoring batch size must be positive")
    if start_sequence < 0 or start_sequence > len(trials):
        raise ValueError("AASIST resume sequence is outside the protocol")
    root = Path(corpus_root).resolve()
    for offset in range(start_sequence, len(trials), batch_size):
        batch_trials = tuple(trials[offset : offset + batch_size])
        decoded = tuple(reader.read(trial.audio_path) for trial in batch_trials)
        scores = scorer.score_batch(tuple(item.audio for item in decoded))
        if len(scores) != len(batch_trials):
            raise ValueError("countermeasure returned an invalid scoring batch")
        records = tuple(
            Asvspoof2019ScoreRecord(
                sequence=offset + index,
                trial_id=trial.trial_id,
                speaker_id=trial.speaker_id,
                partition=trial.partition,
                label=trial.label,
                attack_id=trial.attack_id,
                audio_relative_path=trial.audio_path.resolve().relative_to(root).as_posix(),
                audio_sha256=audio.source_sha256,
                audio_bytes=audio.source_bytes,
                spoof_logit=score.spoof_logit,
                bonafide_logit=score.bonafide_logit,
                spoof_probability=score.spoof_probability,
            )
            for index, (trial, audio, score) in enumerate(
                zip(batch_trials, decoded, scores, strict=True)
            )
        )
        if on_batch is not None:
            on_batch(records)
        yield from records
