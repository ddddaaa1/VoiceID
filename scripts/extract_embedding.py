"""Extract an ECAPA embedding from a local PCM WAVE file without printing biometric data."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from voiceid.adapters.audio.energy_vad import EnergyVoiceActivityDetector
from voiceid.adapters.audio.wave_decoder import PcmWaveDecoder
from voiceid.adapters.models.speechbrain_ecapa import SpeechBrainEcapaEmbedder
from voiceid.application.preprocessing import AudioPreprocessor


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path, help="16-bit PCM WAVE file")
    parser.add_argument("--device", default="cpu", choices=("cpu", "mps", "cuda"))
    arguments = parser.parse_args()

    payload = arguments.audio.read_bytes()
    preprocessing = AudioPreprocessor(PcmWaveDecoder(), EnergyVoiceActivityDetector())
    result = preprocessing.process(payload)
    embedder = SpeechBrainEcapaEmbedder(device=arguments.device)
    embedding = embedder.embed(result.processed)

    norm = math.sqrt(sum(value * value for value in embedding))
    print(f"model={embedder.model_id}")
    print(f"dimension={len(embedding)}")
    print(f"l2_norm={norm:.6f}")
    print(f"speech_seconds={result.quality.speech_seconds:.3f}")
    print("embedding_values=redacted")


if __name__ == "__main__":
    main()
