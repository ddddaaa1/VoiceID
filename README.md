# VoiceID

VoiceID is a **speaker verification and voice attack detection platform**. Its purpose is not to recognize what was said, but to determine whether a voice sample belongs to an enrolled identity and whether the audio appears authentic.

The repository combines a same-origin web experience, a versioned HTTP API, and a tested, framework-independent domain core. The roadmap adds biometric evaluation, anti-spoofing, secure storage, and MLOps.

## What this project demonstrates

- Audio processing: normalization, voice activity detection, quality analysis, and segmentation.
- Deep learning: ECAPA-TDNN speaker embeddings and anti-spoofing classification.
- Biometric logic: enrollment, robust centroids, cosine scoring, and calibration.
- Evaluation: FAR, FRR, EER, ROC-AUC, minDCF, and condition-based analysis.
- Architecture: decoupled domain logic, model adapters, APIs, workers, and events.
- MLOps: versioned datasets, experiment tracking, a model registry, and monitoring.
- Security and privacy: revocable templates, encryption, consent, and retention policies.

## Target architecture

```mermaid
flowchart LR
    W[Web / SDK] --> A[API Gateway]
    A --> O[Verification Orchestrator]
    O --> Q[Audio Quality + VAD]
    Q --> E[Speaker Embedder]
    Q --> S[Anti-spoof Model]
    E --> D[Decision Engine]
    S --> D
    D --> A
    O --> P[(PostgreSQL)]
    O --> B[(Encrypted Object Store)]
    A --> R[(Redis / Job Queue)]
    R --> K[GPU Workers]
    K --> M[Model Registry]
    D --> T[Metrics + Drift Monitoring]
```

See [the architecture document](docs/architecture.md) for component boundaries, evaluation criteria, the threat model, and the delivery roadmap.

Progress is tracked explicitly in the [delivery roadmap](docs/roadmap.md).

## Current status

- Browser-based enrollment and verification connected to the real API and ECAPA model.
- Python core for robust enrollment, cosine scoring, and anti-spoofing decision fusion.
- Defensive PCM WAVE decoding, 16 kHz resampling, signal normalization, and quality analysis.
- Replaceable energy-based VAD baseline with explicit speech segments.
- Real 192-dimensional ECAPA-TDNN speaker embeddings through a lazy SpeechBrain adapter.
- Multi-sample enrollment with quality gates, outlier rejection, and versioned templates.
- One-to-one speaker verification with auditable decisions and provisional policy versioning.
- Versioned FastAPI endpoints with bounded multipart uploads and stable error contracts.
- Unit and contract tests covering audio capture encoding, the API, and biometric logic.
- Leakage-resistant scored-trial manifests with development-only minDCF threshold selection.
- Hash-locked PCM WAVE trial manifests and a real preprocessing + ECAPA scoring runner.
- Deterministic LibriSpeech clean-subset import with provenance, license, and archive checksums.
- Target architecture and incremental roadmap.

The system remains experimental: its decision policy is not calibrated and anti-spoofing is not enabled. It must not be treated as a production biometric authentication system.

## Install the ML environment

The lockfile makes the local ML environment reproducible:

```bash
uv sync --extra ml --extra api --extra dev
```

Extract and validate an embedding from a 16-bit PCM WAVE file:

```bash
uv run python scripts/extract_embedding.py path/to/sample.wav
```

The command reports the model identifier, dimension, norm, and usable speech duration. It intentionally does not print the embedding values.

Run an ephemeral multi-sample enrollment:

```bash
uv run python scripts/enroll_identity.py demo-user sample-1.wav sample-2.wav sample-3.wav
```

This command exercises the real preprocessing and ECAPA pipeline but deliberately uses in-memory persistence. Durable biometric storage is scheduled for Step 9.

Run the complete ephemeral enrollment and verification workflow:

```bash
uv run python scripts/verify_identity.py demo-user sample-1.wav sample-2.wav sample-3.wav \
  --probe probe.wav
```

The initial `provisional-cosine-v1` policy is useful for integration testing only. It has not been calibrated to a measured FAR, FRR, or EER.

Start the application:

```bash
uv run uvicorn voiceid.adapters.api.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` for the microphone workflow. Localhost is a secure browser context, so microphone capture is available after permission is granted. The interactive API contract remains at `http://127.0.0.1:8000/docs`.

Read the [web workflow guide](docs/web.md) and [HTTP API guide](docs/api.md) for implementation details and limitations.

## Run the tests

```bash
uv run python -W error -m unittest discover -s tests -v
node --test tests/web/audio.test.mjs
uv run ruff check .
```

## Next milestone

Score the reproducible LibriSpeech clean cohort and publish a measured calibration report. The importer, audio runner, metric layer, and strict contracts are available:

```bash
uv run python scripts/prepare_librispeech.py \
  --dev-clean data/raw/librispeech/LibriSpeech/dev-clean \
  --test-clean data/raw/librispeech/LibriSpeech/test-clean \
  --output data/raw/librispeech/voiceid-clean-v1
```

Then run the generated hash-locked manifest:

```bash
uv run python scripts/score_audio_trials.py path/to/audio-trials.json \
  --output /tmp/voiceid-scored-trials.json \
  --report /tmp/voiceid-evaluation-report.json
```

Use [the audio manifest template](examples/evaluation/audio-trials.example.json) for a different authorized corpus. The bundled examples are contract fixtures, not VoiceID accuracy results. LibriSpeech's public license is not individual biometric consent, and the generated audio remains ignored by Git. Read the [evaluation protocol](docs/evaluation.md) before interpreting a report.

## Engineering decisions

Important tradeoffs are recorded as Architecture Decision Records:

- [ADR 0001: Use a replaceable audio preprocessing pipeline](docs/decisions/0001-replaceable-audio-pipeline.md)
- [ADR 0002: Start with a pretrained ECAPA-TDNN speaker encoder](docs/decisions/0002-pretrained-ecapa-speaker-encoder.md)
- [ADR 0003: Keep the initial verification policy explicitly provisional](docs/decisions/0003-provisional-verification-policy.md)
- [ADR 0004: Expose a versioned HTTP boundary without coupling it to ML frameworks](docs/decisions/0004-versioned-http-api.md)
- [ADR 0005: Serve a same-origin web client with client-side PCM capture](docs/decisions/0005-same-origin-web-client.md)
- [ADR 0006: Calibrate on speaker-disjoint development trials](docs/decisions/0006-speaker-disjoint-calibration.md)
- [ADR 0007: Bind evaluation trials to hashed audio assets](docs/decisions/0007-hashed-audio-trials.md)

Model behavior, provenance, intended use, and limitations are documented in the [ECAPA-TDNN model card](docs/models/ecapa-tdnn.md).

## Technical references

- [SpeechBrain ECAPA-TDNN](https://speechbrain.readthedocs.io/en/stable/API/speechbrain.lobes.models.ECAPA_TDNN.html)
- [SpeechBrain VoxCeleb pretrained model](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb)
- [ASVspoof 2021](https://www.asvspoof.org/index2021.html)
- [MLflow Tracking](https://mlflow.org/docs/latest/tracking)

## Safety notice

Voice embeddings are biometric data. This project is currently intended for research and portfolio demonstration only. Production use would require informed consent, a documented retention policy, encryption, revocation, bias analysis, and jurisdiction-specific legal review.
