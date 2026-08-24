"""Strict ASVspoof 2019 LA protocol and FLAC corpus adapters."""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path

from voiceid.domain.audio import AudioBuffer
from voiceid.domain.evaluation import TrialPartition
from voiceid.domain.spoofing import SpoofLabel

_ATTACK_ID = re.compile(r"A\d{2}")
_EXPECTED_COUNTS = {
    TrialPartition.DEVELOPMENT: (24_844, 2_548, 22_296),
    TrialPartition.EVALUATION: (71_237, 7_355, 63_882),
}


class Asvspoof2019CorpusError(ValueError):
    """Raised when the official corpus or protocol violates its frozen contract."""


@dataclass(frozen=True, slots=True)
class Asvspoof2019LaTrial:
    speaker_id: str
    trial_id: str
    partition: TrialPartition
    attack_id: str
    label: SpoofLabel
    audio_path: Path


@dataclass(frozen=True, slots=True)
class Asvspoof2019LaProtocol:
    corpus_root: Path
    development_protocol_sha256: str
    evaluation_protocol_sha256: str
    trials: tuple[Asvspoof2019LaTrial, ...]

    def trials_for(self, partition: TrialPartition) -> tuple[Asvspoof2019LaTrial, ...]:
        return tuple(trial for trial in self.trials if trial.partition is partition)


@dataclass(frozen=True, slots=True)
class DecodedCorpusAudio:
    audio: AudioBuffer
    source_sha256: str
    source_bytes: int


def load_asvspoof2019_la_protocol(
    corpus_root: Path,
    *,
    require_official_counts: bool = True,
) -> Asvspoof2019LaProtocol:
    """Load the official five-column LA development and evaluation CM protocols."""

    root = corpus_root.resolve()
    protocol_root = root / "ASVspoof2019_LA_cm_protocols"
    development_path = protocol_root / "ASVspoof2019.LA.cm.dev.trl.txt"
    evaluation_path = protocol_root / "ASVspoof2019.LA.cm.eval.trl.txt"
    development_payload = _read_bounded(development_path, 10_000_000)
    evaluation_payload = _read_bounded(evaluation_path, 20_000_000)
    development = _parse_protocol(
        development_payload,
        root,
        TrialPartition.DEVELOPMENT,
        "ASVspoof2019_LA_dev",
    )
    evaluation = _parse_protocol(
        evaluation_payload,
        root,
        TrialPartition.EVALUATION,
        "ASVspoof2019_LA_eval",
    )
    if require_official_counts:
        _validate_counts(development, TrialPartition.DEVELOPMENT)
        _validate_counts(evaluation, TrialPartition.EVALUATION)
    trial_ids = [trial.trial_id for trial in (*development, *evaluation)]
    if len(trial_ids) != len(set(trial_ids)):
        raise Asvspoof2019CorpusError("ASVspoof trial identifiers must be globally unique")
    development_speakers = {trial.speaker_id for trial in development}
    evaluation_speakers = {trial.speaker_id for trial in evaluation}
    overlap = development_speakers & evaluation_speakers
    if overlap:
        raise Asvspoof2019CorpusError("ASVspoof development/evaluation speaker leakage")
    return Asvspoof2019LaProtocol(
        corpus_root=root,
        development_protocol_sha256=hashlib.sha256(development_payload).hexdigest(),
        evaluation_protocol_sha256=hashlib.sha256(evaluation_payload).hexdigest(),
        trials=(*development, *evaluation),
    )


class SoundFileCorpusReader:
    """Decode bounded, mono FLAC corpus assets and bind scores to source hashes."""

    def __init__(
        self,
        corpus_root: Path,
        *,
        maximum_file_bytes: int = 10_000_000,
        maximum_duration_seconds: float = 30.0,
    ) -> None:
        if maximum_file_bytes <= 0 or maximum_duration_seconds <= 0:
            raise ValueError("corpus reader limits must be positive")
        self._root = corpus_root.resolve()
        self._maximum_file_bytes = maximum_file_bytes
        self._maximum_duration_seconds = maximum_duration_seconds

    def read(self, path: Path) -> DecodedCorpusAudio:
        resolved = path.resolve()
        if path.is_symlink() or not resolved.is_relative_to(self._root):
            raise Asvspoof2019CorpusError("corpus audio path escapes the authorized root")
        payload = _read_bounded(resolved, self._maximum_file_bytes)
        try:
            import soundfile

            samples, sample_rate = soundfile.read(
                io.BytesIO(payload),
                dtype="float32",
                always_2d=True,
            )
        except (ImportError, RuntimeError, TypeError, ValueError) as error:
            raise Asvspoof2019CorpusError("corpus audio is not a decodable FLAC asset") from error
        if sample_rate != 16_000:
            raise Asvspoof2019CorpusError("ASVspoof LA audio must be sampled at 16 kHz")
        if len(samples.shape) != 2 or samples.shape[1] != 1 or samples.shape[0] == 0:
            raise Asvspoof2019CorpusError("ASVspoof LA audio must be non-empty and mono")
        if samples.shape[0] / sample_rate > self._maximum_duration_seconds:
            raise Asvspoof2019CorpusError("ASVspoof LA audio exceeds the duration limit")
        try:
            audio = AudioBuffer(tuple(float(value) for value in samples[:, 0]), sample_rate)
        except ValueError as error:
            raise Asvspoof2019CorpusError("ASVspoof LA audio contains invalid samples") from error
        return DecodedCorpusAudio(
            audio=audio,
            source_sha256=hashlib.sha256(payload).hexdigest(),
            source_bytes=len(payload),
        )


def _parse_protocol(
    payload: bytes,
    root: Path,
    partition: TrialPartition,
    audio_directory: str,
) -> tuple[Asvspoof2019LaTrial, ...]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise Asvspoof2019CorpusError("ASVspoof protocol is not UTF-8") from error
    trials: list[Asvspoof2019LaTrial] = []
    seen: set[str] = set()
    for line_number, line in enumerate(lines, 1):
        fields = line.split()
        if len(fields) != 5:
            raise Asvspoof2019CorpusError(
                f"invalid ASVspoof protocol line {line_number}: expected five fields"
            )
        speaker_id, trial_id, _, attack_id, raw_label = fields
        if not speaker_id.startswith("LA_") or not trial_id.startswith("LA_"):
            raise Asvspoof2019CorpusError("invalid ASVspoof LA identifier")
        if trial_id in seen:
            raise Asvspoof2019CorpusError("duplicate ASVspoof trial identifier")
        seen.add(trial_id)
        try:
            label = SpoofLabel(raw_label)
        except ValueError as error:
            raise Asvspoof2019CorpusError("invalid ASVspoof trial label") from error
        if label is SpoofLabel.BONAFIDE:
            if attack_id != "-":
                raise Asvspoof2019CorpusError("bonafide ASVspoof trial has an attack ID")
            normalized_attack = "bonafide"
        else:
            if _ATTACK_ID.fullmatch(attack_id) is None:
                raise Asvspoof2019CorpusError("spoof ASVspoof trial lacks a valid attack ID")
            normalized_attack = attack_id
        trials.append(
            Asvspoof2019LaTrial(
                speaker_id=speaker_id,
                trial_id=trial_id,
                partition=partition,
                attack_id=normalized_attack,
                label=label,
                audio_path=root / audio_directory / "flac" / f"{trial_id}.flac",
            )
        )
    if not trials:
        raise Asvspoof2019CorpusError("ASVspoof protocol contains no trials")
    return tuple(trials)


def _validate_counts(trials: tuple[Asvspoof2019LaTrial, ...], partition: TrialPartition) -> None:
    expected_total, expected_bonafide, expected_spoof = _EXPECTED_COUNTS[partition]
    bonafide = sum(trial.label is SpoofLabel.BONAFIDE for trial in trials)
    spoof = len(trials) - bonafide
    if (len(trials), bonafide, spoof) != (expected_total, expected_bonafide, expected_spoof):
        raise Asvspoof2019CorpusError(f"unexpected official {partition.value} trial counts")


def _read_bounded(path: Path, maximum_bytes: int) -> bytes:
    try:
        stat = path.stat()
        if not path.is_file() or stat.st_size <= 0 or stat.st_size > maximum_bytes:
            raise Asvspoof2019CorpusError("ASVspoof input violates its size contract")
        return path.read_bytes()
    except OSError as error:
        raise Asvspoof2019CorpusError(f"ASVspoof input is unavailable: {path.name}") from error
