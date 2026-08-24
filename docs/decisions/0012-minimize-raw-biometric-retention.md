# ADR 0012: Do not retain raw audio by default

- **Status:** Accepted
- **Date:** 2026-08-25

## Context

Raw voice recordings contain speech content, background information, and biometric signals. An
encrypted object store would reduce some storage risks but would still create a high-value corpus,
expand consent and deletion obligations, and require an operational KMS and access-control plane.
The current enrollment and verification product does not need recordings after inference.

## Decision

The API does not intentionally persist raw enrollment or probe audio. It persists only an encrypted,
revocable speaker template plus consent and audit metadata. Temporary multipart spooling is bounded
and request-scoped. Dataset audio for offline experiments remains outside the application store,
hash-locked, ignored by Git, and governed by its source license or participant consent.

An object-store adapter will be added only for a concrete evidence-retention or asynchronous-job use
case with a separately approved purpose, retention period, envelope encryption, deletion workflow,
and authorization model.

## Consequences

Data minimization materially reduces breach impact and operational complexity. It also means failed
attempts cannot be replayed from production storage for debugging, so diagnostics must rely on
non-biometric reason codes, metrics, and explicitly consented test corpora.
