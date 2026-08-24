# ADR 0002: Start with a Pretrained ECAPA-TDNN Speaker Encoder

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

VoiceID needs a credible speaker-verification baseline before investing in training infrastructure. Training a speaker encoder from scratch would require a large licensed corpus, substantial compute, augmentation recipes, and careful evaluation. It would delay validation of enrollment, scoring, calibration, and product architecture.

The encoder must expose speaker embeddings rather than final identity labels so that VoiceID can own template construction and decision policy.

## Decision

Use SpeechBrain's pretrained `speechbrain/spkrec-ecapa-voxceleb` model as the first speaker encoder. The upstream model:

- implements ECAPA-TDNN;
- was trained on VoxCeleb1 and VoxCeleb2;
- accepts 16 kHz single-channel waveforms;
- produces 192-dimensional speaker embeddings;
- uses cosine similarity for its documented verification baseline.

Wrap the model behind the `SpeakerEmbedder` port. Load Torch, SpeechBrain, and model weights lazily. Pass only detected speech to the encoder, validate the embedding dimension, and apply L2 normalization before returning a domain vector.

## Consequences

### Positive

- The project immediately uses a recognized speaker-verification architecture.
- Enrollment, scoring, evaluation, and APIs can be built against real embeddings.
- The model remains replaceable behind a stable application port.
- Local unit tests use a fake runtime and do not download model weights.

### Negative

- Upstream performance does not establish VoiceID performance.
- VoxCeleb domain, language, demographic, and recording biases may transfer to the system.
- Model loading adds significant memory, latency, and dependency cost.
- The upstream model repository must eventually be pinned to an immutable revision.

VoiceID will not advertise the upstream EER as its own result. A versioned evaluation protocol must establish project-specific metrics before any security claim is made.
