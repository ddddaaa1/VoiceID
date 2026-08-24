#!/usr/bin/env python3
"""Verify a VoiceID model release and all repository-local evidence hashes."""

from __future__ import annotations

import argparse
from pathlib import Path

from voiceid.adapters.models.release_registry import ModelReleaseError, verify_model_release


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    arguments = parser.parse_args()
    try:
        release = verify_model_release(arguments.release, arguments.repository_root)
    except ModelReleaseError as error:
        parser.error(str(error))
    print(f"release_id={release.release_id}")
    print(f"status={release.status}")
    print(f"models={len(release.model_ids)}")
    print(f"verified_local_artifacts={release.verified_local_artifacts}")
    print(f"verified_evidence={release.verified_evidence}")


if __name__ == "__main__":
    main()
