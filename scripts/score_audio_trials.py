"""Generate VoiceID scored trials from a hashed PCM WAVE corpus."""

from __future__ import annotations

import argparse
from pathlib import Path

from voiceid.adapters.audio.energy_vad import EnergyVoiceActivityDetector
from voiceid.adapters.audio.wave_decoder import PcmWaveDecoder
from voiceid.adapters.evaluation.filesystem import HashedAudioFileReader
from voiceid.adapters.evaluation.json_audio_manifest import load_audio_trial_manifest
from voiceid.adapters.evaluation.json_manifest import (
    ManifestFormatError,
    write_evaluation_report,
    write_scored_trial_manifest,
)
from voiceid.adapters.models.speechbrain_ecapa import SpeechBrainEcapaEmbedder
from voiceid.adapters.repositories.memory import InMemoryVoiceTemplateRepository
from voiceid.application.enrollment import EnrollmentService
from voiceid.application.evaluation import evaluate_scored_trials
from voiceid.application.preprocessing import AudioPreprocessor
from voiceid.application.trial_scoring import AudioTrialScorer, TrialScoringError
from voiceid.application.verification import VerificationService
from voiceid.domain.metrics import DetectionCostModel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Hashed audio-trial JSON manifest")
    parser.add_argument("--output", required=True, type=Path, help="Scored manifest path")
    parser.add_argument("--report", type=Path, help="Optional calibrated report path")
    parser.add_argument("--device", default="cpu", choices=("cpu", "mps", "cuda"))
    parser.add_argument("--max-file-bytes", type=int, default=10_000_000)
    parser.add_argument(
        "--audio-root",
        type=Path,
        help="Optional root for manifest audio paths (defaults to the manifest directory)",
    )
    parser.add_argument("--target-probability", type=float, default=0.01)
    parser.add_argument("--false-accept-cost", type=float, default=1.0)
    parser.add_argument("--false-reject-cost", type=float, default=1.0)
    parser.add_argument("--confidence-level", type=float, default=0.95)
    arguments = parser.parse_args()

    if arguments.manifest.resolve() == arguments.output.resolve():
        parser.error("output must not overwrite the input manifest")

    preprocessor = AudioPreprocessor(PcmWaveDecoder(), EnergyVoiceActivityDetector())
    embedder = SpeechBrainEcapaEmbedder(device=arguments.device)
    repository = InMemoryVoiceTemplateRepository()
    scorer = AudioTrialScorer(
        EnrollmentService(preprocessor, embedder, repository),
        VerificationService(preprocessor, embedder, repository),
        HashedAudioFileReader(
            arguments.audio_root or arguments.manifest.parent,
            max_file_bytes=arguments.max_file_bytes,
        ),
    )

    try:
        manifest = load_audio_trial_manifest(arguments.manifest)
        scored = scorer.score(manifest)
        write_scored_trial_manifest(scored, arguments.output)
        if arguments.report:
            cost_model = DetectionCostModel(
                target_probability=arguments.target_probability,
                false_accept_cost=arguments.false_accept_cost,
                false_reject_cost=arguments.false_reject_cost,
            )
            write_evaluation_report(
                evaluate_scored_trials(
                    scored,
                    cost_model,
                    confidence_level=arguments.confidence_level,
                ),
                arguments.report,
            )
    except (ManifestFormatError, TrialScoringError, ValueError, OSError) as error:
        parser.error(str(error))

    print(f"scored_manifest={arguments.output}")
    print(f"trials={len(scored.trials)}")
    print(f"model={scored.model_id}")
    print(f"pipeline={scored.pipeline_id}")
    if arguments.report:
        print(f"report={arguments.report}")


if __name__ == "__main__":
    main()
