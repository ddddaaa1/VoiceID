"""Strict reader for ASVspoof 2021 Logical Access metadata and CM scores."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


class AsvspoofProtocolError(ValueError):
    """Raised when official metadata and submitted scores do not align."""


@dataclass(frozen=True, slots=True)
class AsvspoofScores:
    bonafide: tuple[float, ...]
    spoof: tuple[float, ...]
    metadata_sha256: str
    scores_sha256: str
    subset: str
    attacks: tuple[str, ...]


def load_la_scores(
    metadata_path: Path,
    scores_path: Path,
    *,
    subset: str = "eval",
) -> AsvspoofScores:
    """Join an official LA CM protocol to a two-column score file by trial ID."""

    if subset not in {"progress", "eval", "hidden"}:
        raise AsvspoofProtocolError("unsupported ASVspoof subset")
    metadata_payload = _read_bounded(metadata_path, 100_000_000)
    scores_payload = _read_bounded(scores_path, 100_000_000)
    selected: dict[str, tuple[str, str]] = {}
    for line_number, line in enumerate(metadata_payload.decode("utf-8").splitlines(), 1):
        fields = line.split()
        if len(fields) != 8:
            raise AsvspoofProtocolError(
                f"invalid LA metadata at line {line_number}: expected 8 fields"
            )
        _, trial_id, _, _, attack_id, label, _, trial_subset = fields
        if label not in {"bonafide", "spoof"}:
            raise AsvspoofProtocolError(f"invalid label at metadata line {line_number}")
        if trial_subset == subset:
            if trial_id in selected:
                raise AsvspoofProtocolError("duplicate trial in ASVspoof metadata")
            selected[trial_id] = (label, attack_id)
    if not selected:
        raise AsvspoofProtocolError("ASVspoof subset contains no trials")

    scores: dict[str, float] = {}
    for line_number, line in enumerate(scores_payload.decode("utf-8").splitlines(), 1):
        fields = line.split()
        if len(fields) != 2:
            raise AsvspoofProtocolError(
                f"invalid score file at line {line_number}: expected 2 fields"
            )
        trial_id, raw_score = fields
        if trial_id in scores:
            raise AsvspoofProtocolError("duplicate trial in ASVspoof scores")
        try:
            score = float(raw_score)
        except ValueError as error:
            raise AsvspoofProtocolError(f"invalid numeric score at line {line_number}") from error
        scores[trial_id] = score

    missing = selected.keys() - scores.keys()
    if missing:
        raise AsvspoofProtocolError(f"scores are missing {len(missing)} selected protocol trials")
    bonafide = tuple(
        scores[trial_id] for trial_id, (label, _) in selected.items() if label == "bonafide"
    )
    spoof = tuple(scores[trial_id] for trial_id, (label, _) in selected.items() if label == "spoof")
    return AsvspoofScores(
        bonafide=bonafide,
        spoof=spoof,
        metadata_sha256=hashlib.sha256(metadata_payload).hexdigest(),
        scores_sha256=hashlib.sha256(scores_payload).hexdigest(),
        subset=subset,
        attacks=tuple(
            sorted(
                {
                    attack
                    for label, attack in selected.values()
                    if label == "spoof" and attack != "-"
                }
            )
        ),
    )


def _read_bounded(path: Path, maximum_bytes: int) -> bytes:
    try:
        if path.stat().st_size > maximum_bytes:
            raise AsvspoofProtocolError("ASVspoof input exceeds the size limit")
        return path.read_bytes()
    except OSError as error:
        raise AsvspoofProtocolError("ASVspoof input is unavailable") from error
