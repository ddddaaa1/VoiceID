from __future__ import annotations

import hashlib
import math
import tempfile
import unittest
from pathlib import Path

import soundfile

from voiceid.adapters.evaluation.asvspoof2019_audio import (
    Asvspoof2019CorpusError,
    SoundFileCorpusReader,
    load_asvspoof2019_la_protocol,
)
from voiceid.domain.evaluation import TrialPartition


class Asvspoof2019ProtocolTests(unittest.TestCase):
    def test_loads_hashes_and_speaker_disjoint_five_field_protocols(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protocols = root / "ASVspoof2019_LA_cm_protocols"
            protocols.mkdir()
            development = b"LA_0001 LA_D_1 - - bonafide\nLA_0001 LA_D_2 - A01 spoof\n"
            evaluation = b"LA_0002 LA_E_1 - - bonafide\nLA_0002 LA_E_2 - A07 spoof\n"
            (protocols / "ASVspoof2019.LA.cm.dev.trl.txt").write_bytes(development)
            (protocols / "ASVspoof2019.LA.cm.eval.trl.txt").write_bytes(evaluation)

            loaded = load_asvspoof2019_la_protocol(root, require_official_counts=False)

            self.assertEqual(len(loaded.trials), 4)
            self.assertEqual(
                loaded.development_protocol_sha256,
                hashlib.sha256(development).hexdigest(),
            )
            self.assertEqual(
                loaded.trials_for(TrialPartition.EVALUATION)[1].audio_path,
                root.resolve() / "ASVspoof2019_LA_eval/flac/LA_E_2.flac",
            )

    def test_rejects_speaker_leakage_and_malformed_labels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protocols = root / "ASVspoof2019_LA_cm_protocols"
            protocols.mkdir()
            development_path = protocols / "ASVspoof2019.LA.cm.dev.trl.txt"
            evaluation_path = protocols / "ASVspoof2019.LA.cm.eval.trl.txt"
            development_path.write_text("LA_1 LA_D_1 - - bonafide\n", encoding="utf-8")
            evaluation_path.write_text("LA_1 LA_E_1 - A07 spoof\n", encoding="utf-8")
            with self.assertRaisesRegex(Asvspoof2019CorpusError, "speaker leakage"):
                load_asvspoof2019_la_protocol(root, require_official_counts=False)

            evaluation_path.write_text("LA_2 LA_E_1 - - spoof\n", encoding="utf-8")
            with self.assertRaisesRegex(Asvspoof2019CorpusError, "attack ID"):
                load_asvspoof2019_la_protocol(root, require_official_counts=False)


class SoundFileCorpusReaderTests(unittest.TestCase):
    def test_decodes_mono_flac_and_hashes_exact_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "sample.flac"
            samples = [0.1 * math.sin(2 * math.pi * 220 * index / 16_000) for index in range(1600)]
            soundfile.write(path, samples, 16_000, format="FLAC", subtype="PCM_16")
            payload = path.read_bytes()

            decoded = SoundFileCorpusReader(root).read(path)

            self.assertEqual(decoded.audio.sample_rate, 16_000)
            self.assertEqual(len(decoded.audio.samples), 1600)
            self.assertEqual(decoded.source_sha256, hashlib.sha256(payload).hexdigest())
            self.assertEqual(decoded.source_bytes, len(payload))

    def test_rejects_paths_outside_the_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            root.mkdir()
            outside = Path(directory) / "outside.flac"
            outside.write_bytes(b"not-audio")
            with self.assertRaisesRegex(Asvspoof2019CorpusError, "authorized root"):
                SoundFileCorpusReader(root).read(outside)


if __name__ == "__main__":
    unittest.main()
