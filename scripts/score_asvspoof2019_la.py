#!/usr/bin/env python3
"""Score official ASVspoof 2019 LA dev/eval audio with the frozen AASIST adapter."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from voiceid.adapters.evaluation.asvspoof2019_audio import (
    Asvspoof2019CorpusError,
    SoundFileCorpusReader,
    load_asvspoof2019_la_protocol,
)
from voiceid.adapters.evaluation.asvspoof2019_outputs import write_asvspoof2019_outputs
from voiceid.adapters.evaluation.sqlite_spoof_ledger import (
    SpoofLedgerError,
    SpoofLedgerIdentity,
    SqliteSpoofScoreLedger,
)
from voiceid.adapters.models.aasist import AasistSpoofDetector, SpoofDetectionError
from voiceid.application.asvspoof2019_scoring import score_asvspoof2019_trials

PIPELINE_ID = "asvspoof2019-la-flac-pad64600-aasist-v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus_root", type=Path, help="Extracted ASVspoof2019 LA directory")
    parser.add_argument("--output", type=Path, required=True, help="Final artifact directory")
    parser.add_argument("--state", type=Path, help="Restart-safe SQLite checkpoint")
    parser.add_argument("--device", choices=("cpu", "mps", "cuda"), default="cpu")
    parser.add_argument("--batch-size", type=int, default=16)
    arguments = parser.parse_args()

    try:
        protocol = load_asvspoof2019_la_protocol(arguments.corpus_root)
        detector = AasistSpoofDetector(device=arguments.device)
        state_path = arguments.state or arguments.corpus_root / ".voiceid-aasist-scores.sqlite3"
        identity = SpoofLedgerIdentity(
            dataset_id="asvspoof2019-la",
            dataset_version="zenodo-record-6906306",
            countermeasure_model_id=detector.model_id,
            pipeline_id=PIPELINE_ID,
            development_protocol_sha256=protocol.development_protocol_sha256,
            evaluation_protocol_sha256=protocol.evaluation_protocol_sha256,
            expected_trials=len(protocol.trials),
        )
        reader = SoundFileCorpusReader(protocol.corpus_root)
        started = time.monotonic()
        with SqliteSpoofScoreLedger(state_path, identity) as ledger:
            trial_ids = tuple(trial.trial_id for trial in protocol.trials)
            resume_sequence = ledger.resume_sequence(trial_ids)
            print(f"trials={len(protocol.trials)}")
            print(f"resume_sequence={resume_sequence}")
            print(f"device={arguments.device}")

            def persist(records):
                ledger.append(records)
                completed = records[-1].sequence + 1
                if completed == len(protocol.trials) or completed % 1_000 < len(records):
                    elapsed = max(time.monotonic() - started, 1e-9)
                    rate = (completed - resume_sequence) / elapsed
                    print(f"completed={completed} rate_trials_per_second={rate:.3f}", flush=True)

            for _ in score_asvspoof2019_trials(
                protocol.trials,
                detector,
                reader,
                corpus_root=protocol.corpus_root,
                start_sequence=resume_sequence,
                batch_size=arguments.batch_size,
                on_batch=persist,
            ):
                pass
            records = ledger.records()
        artifacts = write_asvspoof2019_outputs(
            records,
            protocol,
            arguments.output,
            asv_scores_path=(
                protocol.corpus_root
                / "ASVspoof2019_LA_asv_scores"
                / "ASVspoof2019.LA.asv.eval.gi.trl.scores.txt"
            ),
            countermeasure_model_id=detector.model_id,
            pipeline_id=PIPELINE_ID,
        )
    except (Asvspoof2019CorpusError, SpoofDetectionError, SpoofLedgerError, ValueError) as error:
        parser.error(str(error))

    print(f"output={arguments.output}")
    print(f"inventory_sha256={artifacts.inventory_sha256}")
    print(f"report_sha256={artifacts.report_sha256}")


if __name__ == "__main__":
    main()
