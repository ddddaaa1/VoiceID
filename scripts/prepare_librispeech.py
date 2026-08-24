"""Build a deterministic, hash-locked VoiceID corpus from LibriSpeech clean subsets."""

from __future__ import annotations

import argparse
from pathlib import Path

from voiceid.adapters.evaluation.librispeech import LibriSpeechCorpusPreparer
from voiceid.application.librispeech import CorpusPreparationError, LibriSpeechImportConfig


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev-clean", required=True, type=Path, help="Extracted dev-clean root")
    parser.add_argument("--test-clean", required=True, type=Path, help="Extracted test-clean root")
    parser.add_argument("--output", required=True, type=Path, help="New output directory")
    parser.add_argument(
        "--dataset-version", default="voiceid-librispeech-clean-v1", help="Immutable version"
    )
    parser.add_argument("--speakers", type=int, default=10, help="Speakers per partition")
    parser.add_argument("--enrollment-clips", type=int, default=3)
    parser.add_argument("--probe-clips", type=int, default=3)
    parser.add_argument("--minimum-duration", type=float, default=2.5)
    parser.add_argument("--maximum-duration", type=float, default=12.0)
    parser.add_argument("--seed", default="voiceid-librispeech-v1")
    arguments = parser.parse_args()

    try:
        config = LibriSpeechImportConfig(
            speakers_per_partition=arguments.speakers,
            enrollment_clips_per_speaker=arguments.enrollment_clips,
            probe_clips_per_speaker=arguments.probe_clips,
            minimum_duration_seconds=arguments.minimum_duration,
            maximum_duration_seconds=arguments.maximum_duration,
            selection_seed=arguments.seed,
        )
        manifest = LibriSpeechCorpusPreparer().prepare(
            arguments.dev_clean,
            arguments.test_clean,
            arguments.output,
            dataset_version=arguments.dataset_version,
            config=config,
        )
    except (CorpusPreparationError, OSError) as error:
        parser.error(str(error))

    print(f"manifest={arguments.output / 'audio-trials.json'}")
    print(f"provenance={arguments.output / 'provenance.json'}")
    print(f"enrollments={len(manifest.enrollments)}")
    print(f"trials={len(manifest.trials)}")


if __name__ == "__main__":
    main()
