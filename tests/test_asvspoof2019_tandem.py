from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from voiceid.adapters.evaluation.asvspoof2019_audio import Asvspoof2019CorpusError
from voiceid.adapters.evaluation.asvspoof2019_tandem import evaluate_asvspoof2019_tandem
from voiceid.application.asvspoof2019_scoring import Asvspoof2019ScoreRecord
from voiceid.domain.evaluation import TrialPartition
from voiceid.domain.spoofing import SpoofLabel


def record(sequence: int, label: SpoofLabel, attack: str, score: float) -> Asvspoof2019ScoreRecord:
    return Asvspoof2019ScoreRecord(
        sequence=sequence,
        trial_id=f"LA_E_{sequence}",
        speaker_id="speaker",
        partition=TrialPartition.EVALUATION,
        label=label,
        attack_id=attack,
        audio_relative_path=f"{sequence}.flac",
        audio_sha256=f"{sequence:064x}",
        audio_bytes=100,
        spoof_logit=-score,
        bonafide_logit=score,
        spoof_probability=0.1 if label is SpoofLabel.BONAFIDE else 0.9,
    )


class Asvspoof2019TandemTests(unittest.TestCase):
    def test_derives_official_fixed_asv_coefficients_and_attack_breakdown(self) -> None:
        records = (
            record(0, SpoofLabel.BONAFIDE, "bonafide", 0.9),
            record(1, SpoofLabel.BONAFIDE, "bonafide", 0.8),
            record(2, SpoofLabel.SPOOF, "A07", 0.2),
            record(3, SpoofLabel.SPOOF, "A08", 0.1),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "asv.txt"
            path.write_text(
                "speaker target 0.9\n"
                "speaker target 0.8\n"
                "speaker nontarget 0.2\n"
                "speaker nontarget 0.1\n"
                "speaker spoof 0.85\n"
                "speaker spoof 0.75\n",
                encoding="utf-8",
            )

            report = evaluate_asvspoof2019_tandem(records, path)

            self.assertEqual(report.context.observed_asv_eer, 0.0)
            self.assertGreater(report.context.coefficients.c1, 0.0)
            self.assertGreater(report.context.coefficients.c2, 0.0)
            self.assertEqual(report.pooled.minimum.normalized_cost, 0.0)
            self.assertEqual(set(report.attacks), {"A07", "A08"})

    def test_rejects_missing_asv_classes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "asv.txt"
            path.write_text("speaker target 0.9\n", encoding="utf-8")
            with self.assertRaisesRegex(Asvspoof2019CorpusError, "lacks"):
                evaluate_asvspoof2019_tandem(
                    (
                        record(0, SpoofLabel.BONAFIDE, "bonafide", 0.9),
                        record(1, SpoofLabel.SPOOF, "A07", 0.1),
                    ),
                    path,
                )


if __name__ == "__main__":
    unittest.main()
