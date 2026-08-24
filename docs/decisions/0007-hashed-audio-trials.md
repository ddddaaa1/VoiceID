# ADR 0007: Bind Evaluation Trials to Hashed Audio Assets

- **Status:** Accepted
- **Date:** 2026-08-25

## Context

A scored manifest is reproducible only if the recordings that produced its scores are immutable and traceable. Path names alone do not establish content identity, and a permissive dataset loader could accidentally reuse enrollment recordings as probes, mix speakers across partitions, follow paths outside the dataset, or omit failed trials.

The evaluation runner must reuse the production-shaped preprocessing, enrollment, and verification logic without coupling the domain to filesystems or SpeechBrain.

## Decision

VoiceID introduces `voiceid-audio-trials/v1`. Every PCM WAVE asset is referenced by a safe relative path and lowercase SHA-256 digest. A bounded filesystem adapter resolves paths under the manifest directory, rejects escapes and invalid files, verifies content hashes, and only then returns bytes to the application layer.

The domain contract validates consent metadata, unique enrollment recordings, genuine/impostor labels, claimed identities, speaker-disjoint partitions, audio-content-disjoint partitions, and separation of enrollment and probe audio. Reused probes are permitted only when they retain the same true speaker identity.

An application scoring orchestrator calls the existing enrollment and verification services and emits `voiceid-scored-trials/v1` with the actual model and pipeline identifiers. Any enrollment failure or unavailable probe score fails the run instead of dropping a trial.

## Consequences

- Score provenance is bound to exact audio bytes and versioned system components.
- Filesystem and integrity concerns remain outside domain and application logic.
- Evaluation uses the same core workflow as the HTTP product path.
- Dataset preparation requires explicit hashes and consent documentation.
- SHA-256 detects accidental or malicious content changes but does not encrypt recordings or establish legal consent by itself.
- A consented multi-speaker corpus is still required before publishing accuracy claims.
