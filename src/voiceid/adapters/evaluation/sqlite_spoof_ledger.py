"""Transactional checkpoint ledger for long-running corpus inference."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Self

from voiceid.application.asvspoof2019_scoring import Asvspoof2019ScoreRecord
from voiceid.domain.evaluation import TrialPartition
from voiceid.domain.spoofing import SpoofLabel


class SpoofLedgerError(ValueError):
    """Raised when resume state does not match the frozen scoring run."""


@dataclass(frozen=True, slots=True)
class SpoofLedgerIdentity:
    dataset_id: str
    dataset_version: str
    countermeasure_model_id: str
    pipeline_id: str
    development_protocol_sha256: str
    evaluation_protocol_sha256: str
    expected_trials: int
    schema_version: str = "voiceid-asvspoof2019-score-ledger/v1"

    def __post_init__(self) -> None:
        identifiers = (
            self.dataset_id,
            self.dataset_version,
            self.countermeasure_model_id,
            self.pipeline_id,
        )
        if any(not value or value != value.strip() for value in identifiers):
            raise SpoofLedgerError("checkpoint identity fields are required")
        for digest in (
            self.development_protocol_sha256,
            self.evaluation_protocol_sha256,
        ):
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise SpoofLedgerError("checkpoint protocol hashes must be lowercase SHA-256")
        if self.expected_trials <= 0:
            raise SpoofLedgerError("checkpoint expected trial count must be positive")


class SqliteSpoofScoreLedger:
    """Append exact protocol prefixes atomically and resume after interruption."""

    def __init__(self, path: Path, identity: SpoofLedgerIdentity) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS ledger_metadata (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scored_trials (
                sequence INTEGER PRIMARY KEY CHECK (sequence >= 0),
                trial_id TEXT NOT NULL UNIQUE,
                speaker_id TEXT NOT NULL,
                partition TEXT NOT NULL,
                label TEXT NOT NULL,
                attack_id TEXT NOT NULL,
                audio_relative_path TEXT NOT NULL,
                audio_sha256 TEXT NOT NULL,
                audio_bytes INTEGER NOT NULL CHECK (audio_bytes > 0),
                spoof_logit REAL NOT NULL,
                bonafide_logit REAL NOT NULL,
                spoof_probability REAL NOT NULL
                    CHECK (spoof_probability >= 0 AND spoof_probability <= 1)
            );
            """
        )
        expected = json.dumps(asdict(identity), sort_keys=True, separators=(",", ":"))
        row = self._connection.execute(
            "SELECT payload FROM ledger_metadata WHERE singleton = 1"
        ).fetchone()
        if row is None:
            self._connection.execute(
                "INSERT INTO ledger_metadata(singleton, payload) VALUES (1, ?)",
                (expected,),
            )
            self._connection.commit()
        elif row[0] != expected:
            self._connection.close()
            raise SpoofLedgerError("checkpoint metadata does not match this scoring run")
        self.identity = identity

    def resume_sequence(self, expected_trial_ids: tuple[str, ...]) -> int:
        rows = self._connection.execute(
            "SELECT sequence, trial_id FROM scored_trials ORDER BY sequence"
        ).fetchall()
        if len(rows) > self.identity.expected_trials or len(rows) > len(expected_trial_ids):
            raise SpoofLedgerError("checkpoint contains too many trials")
        for expected_sequence, (sequence, trial_id) in enumerate(rows):
            if sequence != expected_sequence or trial_id != expected_trial_ids[expected_sequence]:
                raise SpoofLedgerError("checkpoint is not an exact protocol prefix")
        return len(rows)

    def append(self, records: tuple[Asvspoof2019ScoreRecord, ...]) -> None:
        if not records:
            raise SpoofLedgerError("cannot append an empty scoring batch")
        current = self._connection.execute("SELECT COUNT(*) FROM scored_trials").fetchone()[0]
        if records[0].sequence != current or any(
            record.sequence != current + index for index, record in enumerate(records)
        ):
            raise SpoofLedgerError("scoring batch is not the next protocol suffix")
        try:
            with self._connection:
                self._connection.executemany(
                    """
                    INSERT INTO scored_trials(
                        sequence, trial_id, speaker_id, partition, label, attack_id,
                        audio_relative_path, audio_sha256, audio_bytes, spoof_logit,
                        bonafide_logit, spoof_probability
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            record.sequence,
                            record.trial_id,
                            record.speaker_id,
                            record.partition.value,
                            record.label.value,
                            record.attack_id,
                            record.audio_relative_path,
                            record.audio_sha256,
                            record.audio_bytes,
                            record.spoof_logit,
                            record.bonafide_logit,
                            record.spoof_probability,
                        )
                        for record in records
                    ],
                )
        except sqlite3.IntegrityError as error:
            raise SpoofLedgerError("scoring batch conflicts with checkpoint state") from error

    def records(self) -> tuple[Asvspoof2019ScoreRecord, ...]:
        rows = self._connection.execute(
            """
            SELECT sequence, trial_id, speaker_id, partition, label, attack_id,
                   audio_relative_path, audio_sha256, audio_bytes, spoof_logit,
                   bonafide_logit, spoof_probability
            FROM scored_trials ORDER BY sequence
            """
        ).fetchall()
        return tuple(
            Asvspoof2019ScoreRecord(
                sequence=row[0],
                trial_id=row[1],
                speaker_id=row[2],
                partition=TrialPartition(row[3]),
                label=SpoofLabel(row[4]),
                attack_id=row[5],
                audio_relative_path=row[6],
                audio_sha256=row[7],
                audio_bytes=row[8],
                spoof_logit=row[9],
                bonafide_logit=row[10],
                spoof_probability=row[11],
            )
            for row in rows
        )

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
