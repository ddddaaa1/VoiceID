# ADR 0003: Keep the Initial Verification Policy Explicitly Provisional

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

VoiceID can now compare an ECAPA-TDNN probe embedding with an enrolled template. A numerical similarity is not a decision until a threshold and review region are selected.

No versioned VoiceID evaluation corpus or calibrated operating point exists yet. Reusing an undocumented threshold as if it represented a measured security level would create false confidence. The anti-spoofing countermeasure is also scheduled for a later step.

## Decision

Introduce a versioned policy named `provisional-cosine-v1` with:

- cosine similarity as the speaker score;
- a provisional match threshold of `0.72`;
- a `0.05` review margin below the threshold;
- explicit `spoof_check_not_run` reason codes when no countermeasure is available;
- a `require_spoof_check` option that changes otherwise acceptable attempts to `review`;
- `review` results for quality and model-inference failures.

Every verification attempt records the policy identifier, template version, model identifier, pipeline identifier, scores, decision, and reason codes.

## Consequences

### Positive

- Enrollment and verification can be exercised end to end.
- Results expose missing security signals rather than silently assuming success.
- Policy versions make future threshold changes auditable.
- High-risk callers can require anti-spoofing before it becomes a default.

### Negative

- `accept` currently means “accepted by the provisional speaker-only policy,” not production authentication.
- The numeric threshold has no project-specific FAR or FRR guarantee.
- Scores are not yet calibrated across devices, languages, or recording conditions.

Step 7 must replace this policy with thresholds derived from disjoint development and evaluation trials. Step 8 must add and evaluate the anti-spoofing countermeasure before VoiceID makes authentication claims.
