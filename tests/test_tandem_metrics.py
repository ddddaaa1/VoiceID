from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from voiceid.adapters.evaluation.asvspoof2021 import (
    AsvspoofProtocolError,
    load_la_scores,
)
from voiceid.domain.tandem_metrics import TandemCoefficients, evaluate_tandem_cost


class TandemMetricTests(unittest.TestCase):
    def test_selects_minimum_official_style_tandem_cost(self) -> None:
        coefficients = TandemCoefficients(c0=0.1, c1=0.6, c2=0.3)
        result = evaluate_tandem_cost(
            bonafide_support_scores=(0.9, 0.8, 0.7),
            spoof_support_scores=(0.4, 0.3, 0.2),
            coefficients=coefficients,
        )

        self.assertEqual(result.minimum.bonafide_reject_rate, 0.0)
        self.assertEqual(result.minimum.spoof_accept_rate, 0.0)
        self.assertTrue(math.isclose(result.minimum.normalized_cost, 0.25))
        self.assertEqual(result.observed_eer, 0.0)

    def test_rejects_invalid_scores_and_coefficients(self) -> None:
        with self.assertRaises(ValueError):
            TandemCoefficients(c0=0.0, c1=0.0, c2=1.0)
        with self.assertRaises(ValueError):
            evaluate_tandem_cost(
                (0.1, float("nan")),
                (0.2,),
                TandemCoefficients(0.1, 0.2, 0.3),
            )


class AsvspoofReaderTests(unittest.TestCase):
    def test_joins_selected_official_la_trials_and_hashes_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / "metadata.txt"
            score_file = root / "scores.txt"
            metadata.write_text(
                "LA_1 LA_D_1 none - - bonafide notrim progress\n"
                "LA_2 LA_E_1 alaw tx A07 spoof notrim eval\n"
                "LA_3 LA_E_2 none - - bonafide notrim eval\n",
                encoding="utf-8",
            )
            score_file.write_text(
                "LA_D_1 0.5\nLA_E_2 2.5\nLA_E_1 -1.5\n",
                encoding="utf-8",
            )

            loaded = load_la_scores(metadata, score_file)

            self.assertEqual(loaded.bonafide, (2.5,))
            self.assertEqual(loaded.spoof, (-1.5,))
            self.assertEqual(loaded.attacks, ("A07",))
            self.assertEqual(len(loaded.metadata_sha256), 64)

    def test_rejects_missing_scores_and_malformed_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / "metadata.txt"
            score_file = root / "scores.txt"
            metadata.write_text(
                "LA_2 LA_E_1 alaw tx A07 spoof notrim eval\n",
                encoding="utf-8",
            )
            score_file.write_text("LA_OTHER 0.1\n", encoding="utf-8")
            with self.assertRaises(AsvspoofProtocolError):
                load_la_scores(metadata, score_file)

            metadata.write_text("not enough fields\n", encoding="utf-8")
            with self.assertRaises(AsvspoofProtocolError):
                load_la_scores(metadata, score_file)


if __name__ == "__main__":
    unittest.main()
