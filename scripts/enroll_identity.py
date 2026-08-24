"""Create an ephemeral VoiceID template from multiple local PCM WAVE samples."""

from __future__ import annotations

import argparse
from pathlib import Path

from voiceid.adapters.audio.energy_vad import EnergyVoiceActivityDetector
from voiceid.adapters.audio.wave_decoder import PcmWaveDecoder
from voiceid.adapters.models.speechbrain_ecapa import SpeechBrainEcapaEmbedder
from voiceid.adapters.repositories.memory import InMemoryVoiceTemplateRepository
from voiceid.application.enrollment import EnrollmentRejected, EnrollmentService
from voiceid.application.preprocessing import AudioPreprocessor


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("identity_id", help="Logical identity to enroll")
    parser.add_argument("audio", nargs="+", type=Path, help="Three or more PCM WAVE files")
    parser.add_argument("--device", default="cpu", choices=("cpu", "mps", "cuda"))
    arguments = parser.parse_args()

    preprocessing = AudioPreprocessor(PcmWaveDecoder(), EnergyVoiceActivityDetector())
    embedder = SpeechBrainEcapaEmbedder(device=arguments.device)
    repository = InMemoryVoiceTemplateRepository()
    service = EnrollmentService(preprocessing, embedder, repository)

    try:
        result = service.enroll(
            arguments.identity_id,
            [audio_path.read_bytes() for audio_path in arguments.audio],
        )
    except EnrollmentRejected as error:
        print(f"enrollment=failed code={error.code}")
        for issue in error.sample_issues:
            print(f"sample={issue.sample_index} reasons={','.join(issue.reasons)}")
        raise SystemExit(2) from error

    template = result.template
    print("enrollment=succeeded")
    print(f"identity_id={template.identity_id}")
    print(f"template_id={template.template_id}")
    print(f"template_version={template.version}")
    print(f"retained_samples={template.sample_count}")
    print(f"discarded_samples={len(result.discarded_samples)}")
    print(f"model={template.model_id}")
    print(f"pipeline={template.pipeline_id}")
    print(f"embedding_dimension={len(template.embedding)}")
    print("embedding_values=redacted")
    print("persistence=ephemeral")


if __name__ == "__main__":
    main()
