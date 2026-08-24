from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from voiceid.adapters.evaluation.asvspoof2019_audio import (
    Asvspoof2019LaProtocol,
    Asvspoof2019LaTrial,
    DecodedCorpusAudio,
)
from voiceid.adapters.evaluation.asvspoof2019_outputs import write_asvspoof2019_outputs
from voiceid.adapters.evaluation.json_spoof_manifest import load_spoof_score_manifest
from voiceid.adapters.evaluation.sqlite_spoof_ledger import (
    SpoofLedgerError,
    SpoofLedgerIdentity,
    SqliteSpoofScoreLedger,
)
from voiceid.adapters.models.aasist import AasistModelScore
from voiceid.application.asvspoof2019_scoring import score_asvspoof2019_trials
from voiceid.domain.audio import AudioBuffer
from voiceid.domain.evaluation import TrialPartition
from voiceid.domain.spoofing import SpoofLabel


class FakeReader:
    def read(self, path: Path) -> DecodedCorpusAudio:
        key = float(path.stem[-1]) / 10.0
        return DecodedCorpusAudio(
            AudioBuffer((key,) * 8000, 16_000),
            f"{int(key * 10):064x}",
            100,
        )


class FakeScorer:
    model_id = "countermeasure-v1"

    def score_batch(self, audio):
        return tuple(
            AasistModelScore(
                spoof_logit=item.samples[0],
                bonafide_logit=1.0 - item.samples[0],
                spoof_probability=item.samples[0],
            )
            for item in audio
        )


def protocol(root: Path) -> Asvspoof2019LaProtocol:
    values = (
        ("LA_D_1", "dev-speaker", TrialPartition.DEVELOPMENT, SpoofLabel.BONAFIDE, "bonafide"),
        ("LA_D_2", "dev-speaker", TrialPartition.DEVELOPMENT, SpoofLabel.SPOOF, "A01"),
        ("LA_E_1", "eval-speaker", TrialPartition.EVALUATION, SpoofLabel.BONAFIDE, "bonafide"),
        ("LA_E_2", "eval-speaker", TrialPartition.EVALUATION, SpoofLabel.SPOOF, "A07"),
    )
    return Asvspoof2019LaProtocol(
        corpus_root=root,
        development_protocol_sha256="a" * 64,
        evaluation_protocol_sha256="b" * 64,
        trials=tuple(
            Asvspoof2019LaTrial(
                speaker_id=speaker,
                trial_id=trial_id,
                partition=partition,
                label=label,
                attack_id=attack,
                audio_path=root / f"{trial_id[-1]}.flac",
            )
            for trial_id, speaker, partition, label, attack in values
        ),
    )


class Asvspoof2019ScoringTests(unittest.TestCase):
    def test_checkpoints_exact_batches_resumes_and_publishes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frozen = protocol(root)
            identity = SpoofLedgerIdentity(
                dataset_id="asvspoof2019-la",
                dataset_version="test",
                countermeasure_model_id="countermeasure-v1",
                pipeline_id="pipeline-v1",
                development_protocol_sha256="a" * 64,
                evaluation_protocol_sha256="b" * 64,
                expected_trials=4,
            )
            state = root / "state.sqlite3"
            with SqliteSpoofScoreLedger(state, identity) as ledger:
                first = tuple(
                    score_asvspoof2019_trials(
                        frozen.trials[:2],
                        FakeScorer(),
                        FakeReader(),
                        corpus_root=root,
                        batch_size=2,
                        on_batch=ledger.append,
                    )
                )
                self.assertEqual(len(first), 2)
                self.assertEqual(
                    ledger.resume_sequence(tuple(trial.trial_id for trial in frozen.trials)),
                    2,
                )
                tuple(
                    score_asvspoof2019_trials(
                        frozen.trials,
                        FakeScorer(),
                        FakeReader(),
                        corpus_root=root,
                        start_sequence=2,
                        batch_size=2,
                        on_batch=ledger.append,
                    )
                )
                records = ledger.records()

            output = root / "output"
            asv_scores = root / "asv-scores.txt"
            asv_scores.write_text(
                "speaker target 0.9\n"
                "speaker target 0.8\n"
                "speaker nontarget 0.2\n"
                "speaker nontarget 0.1\n"
                "speaker spoof 0.85\n"
                "speaker spoof 0.75\n",
                encoding="utf-8",
            )
            artifacts = write_asvspoof2019_outputs(
                records,
                frozen,
                output,
                asv_scores_path=asv_scores,
                countermeasure_model_id="countermeasure-v1",
                pipeline_id="pipeline-v1",
            )
            manifest = load_spoof_score_manifest(output / "spoof-scores.json")

            self.assertEqual(len(manifest.trials), 4)
            self.assertEqual(len(artifacts.inventory_sha256), 64)
            self.assertTrue((output / "countermeasure-report.json").is_file())
            self.assertTrue((output / "official-cm-scores.txt").is_file())
            self.assertTrue((output / "tandem-report.json").is_file())
            self.assertTrue((output / "provenance.json").is_file())

    def test_rejects_checkpoint_identity_or_protocol_prefix_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.sqlite3"
            identity = SpoofLedgerIdentity(
                "dataset", "v1", "model", "pipeline", "a" * 64, "b" * 64, 1
            )
            with SqliteSpoofScoreLedger(state, identity) as ledger:
                self.assertEqual(ledger.resume_sequence(("trial",)), 0)
            changed = SpoofLedgerIdentity(
                "dataset", "v2", "model", "pipeline", "a" * 64, "b" * 64, 1
            )
            with self.assertRaisesRegex(SpoofLedgerError, "metadata"):
                SqliteSpoofScoreLedger(state, changed)


if __name__ == "__main__":
    unittest.main()
