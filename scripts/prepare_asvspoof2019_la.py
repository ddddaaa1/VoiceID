#!/usr/bin/env python3
"""Verify and safely extract the official ASVspoof 2019 Logical Access archive."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from voiceid.adapters.evaluation.asvspoof2019_archive import extract_verified_archive
from voiceid.adapters.evaluation.asvspoof2019_audio import Asvspoof2019CorpusError


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    try:
        provenance = extract_verified_archive(arguments.archive, arguments.destination)
    except Asvspoof2019CorpusError as error:
        parser.error(str(error))
    print(json.dumps(provenance, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
