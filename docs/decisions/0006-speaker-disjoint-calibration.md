# ADR 0006: Calibrate on Speaker-Disjoint Development Trials

- **Status:** Accepted
- **Date:** 2026-08-25

## Context

The provisional cosine threshold allows integration testing but has no measured VoiceID FAR, FRR, EER, or detection cost. Selecting a threshold from the same trials used for the final result would leak evaluation information and produce an optimistic estimate. Splitting recordings while leaving the same speakers in both partitions would still leak speaker characteristics.

## Decision

VoiceID uses versioned scored-trial manifests with speaker-disjoint `development` and `evaluation` partitions. All enrollment and probe speaker identifiers participate in the leakage check, including impostor trials.

The operating threshold is selected only on development trials by normalized minDCF under an explicit target probability and error-cost model. That threshold is then locked for the evaluation partition. Evaluation EER and minDCF are reported as diagnostics but cannot replace the development-selected operating point.

The manifest binds every score to a dataset version, speaker model, preprocessing pipeline, label, and recording condition. Invalid labels, non-finite scores, missing trial classes, duplicate IDs, unknown fields, and speaker overlap fail closed.

## Consequences

- The final report distinguishes threshold selection from generalization measurement.
- Dataset and system versions make results reproducible and auditable.
- Condition breakdowns can expose performance differences hidden by aggregate metrics.
- Small or unbalanced datasets still produce numerically valid but statistically weak estimates; confidence intervals remain required before claims.
- Real audio scoring and a consented corpus are still necessary before replacing `provisional-cosine-v1`.
