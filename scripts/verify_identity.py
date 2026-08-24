"""Enroll and verify an identity locally with real ECAPA-TDNN embeddings."""

from __future__ import annotations

import argparse
from pathlib import Path

from voiceid.adapters.audio.energy_vad import EnergyVoiceActivityDetector
from voiceid.adapters.audio.wave_decoder import PcmWaveDecoder
from voiceid.adapters.models.speechbrain_ecapa import SpeechBrainEcapaEmbedder
from voiceid.adapters.repositories.memory import InMemoryVoiceTemplateRepository
from voiceid.application.enrollment import EnrollmentRejected, EnrollmentService
from voiceid.application.preprocessing import AudioPreprocessor
from voiceid.application.verification import VerificationService, VerificationUnavailable


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("identity_id", help="Logical identity to enroll and verify")
    parser.add_argument("enrollment", nargs="+", type=Path, help="Enrollment PCM WAVE files")
    parser.add_argument("--probe", required=True, type=Path, help="Probe PCM WAVE file")
    parser.add_argument("--device", default="cpu", choices=("cpu", "mps", "cuda"))
    arguments = parser.parse_args()

    preprocessor = AudioPreprocessor(PcmWaveDecoder(), EnergyVoiceActivityDetector())
    embedder = SpeechBrainEcapaEmbedder(device=arguments.device)
    repository = InMemoryVoiceTemplateRepository()
    enrollment_service = EnrollmentService(preprocessor, embedder, repository)
    verification_service = VerificationService(preprocessor, embedder, repository)

    try:
        enrollment_service.enroll(
            arguments.identity_id,
            [audio_path.read_bytes() for audio_path in arguments.enrollment],
        )
        attempt = verification_service.verify(
            arguments.identity_id,
            arguments.probe.read_bytes(),
        )
    except (EnrollmentRejected, VerificationUnavailable) as error:
        print(f"workflow=failed code={error}")
        raise SystemExit(2) from error

    result = attempt.result
    score = "unavailable" if result.speaker_score is None else f"{result.speaker_score:.6f}"
    spoof = (
        "not_run" if result.spoof_probability is None else f"{result.spoof_probability:.6f}"
    )
    print("workflow=succeeded")
    print(f"attempt_id={attempt.attempt_id}")
    print(f"created_at={attempt.created_at.isoformat()}")
    print(f"identity_id={attempt.identity_id}")
    print(f"template_id={attempt.template_id}")
    print(f"template_version={attempt.template_version}")
    print(f"policy={attempt.policy_id}")
    print(f"speaker_score={score}")
    print(f"spoof_probability={spoof}")
    print(f"decision={result.decision.value}")
    print(f"reasons={','.join(result.reasons)}")
    print("persistence=ephemeral")


if __name__ == "__main__":
    main()
