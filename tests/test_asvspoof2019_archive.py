from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from voiceid.adapters.evaluation.asvspoof2019_archive import extract_verified_archive
from voiceid.adapters.evaluation.asvspoof2019_audio import Asvspoof2019CorpusError


class Asvspoof2019ArchiveTests(unittest.TestCase):
    def test_verifies_and_atomically_extracts_safe_la_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "LA.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("LA/README.LA.txt", "authorized fixture")
                output.writestr("LA/ASVspoof2019_LA_dev/flac/sample.flac", b"flac-fixture")
            payload = archive.read_bytes()
            destination = root / "extracted"

            provenance = extract_verified_archive(
                archive,
                destination,
                expected_bytes=len(payload),
                expected_md5=hashlib.md5(payload, usedforsecurity=False).hexdigest(),
                maximum_members=10,
                maximum_uncompressed_bytes=1_000,
            )

            self.assertEqual(
                (destination / "LA/README.LA.txt").read_text(encoding="utf-8"),
                "authorized fixture",
            )
            self.assertEqual(provenance["extraction"]["members"], 2)
            self.assertTrue((destination / "voiceid-acquisition.json").is_file())

    def test_rejects_path_traversal_before_creating_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "LA.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("LA/../outside.txt", "unsafe")
            payload = archive.read_bytes()
            destination = root / "extracted"

            with self.assertRaisesRegex(Asvspoof2019CorpusError, "unsafe"):
                extract_verified_archive(
                    archive,
                    destination,
                    expected_bytes=len(payload),
                    expected_md5=hashlib.md5(payload, usedforsecurity=False).hexdigest(),
                )

            self.assertFalse(destination.exists())
            self.assertFalse((root / "outside.txt").exists())


if __name__ == "__main__":
    unittest.main()
