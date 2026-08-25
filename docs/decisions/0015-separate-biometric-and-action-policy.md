# ADR 0015: Separate Biometric Evidence from Action Authorization

- Status: Accepted
- Date: 2026-08-25

## Context

Speaker verification produces evidence about a claimed identity, not permission to perform an
operation. Treating every accepted voice match as an authorization would give media playback,
private-message access, purchases, and physical access the same assurance requirement. It would
also allow a client-controlled risk label to bypass server policy.

Voice has additional limitations on wearables: the microphone may capture a nearby person, replay,
or synthetic speech, and the device may not prove that the speaker is wearing it. High similarity
therefore cannot be treated as a universal authentication factor.

## Decision

Keep biometric verification and action authorization as separate domain decisions with independent
policy identifiers. Define a closed, server-owned action catalog and map every action to a low,
moderate, or high risk tier.

Low-risk actions may proceed after an accepted voice match. Moderate-risk actions also require
accepted anti-spoofing evidence. High-risk actions always require a device biometric or passkey.
Rejected voices deny the request, while inconclusive evidence requests step-up authentication.

Return the underlying verification attempt inside every authorization response so the decision is
auditable without collapsing distinct evidence into a single unexplained score.

## Consequences

The same voice evidence can safely produce different outcomes for different operations. Clients
cannot downgrade an action by submitting a risk tier. The policy remains easy to unit-test without
FastAPI or ML dependencies.

The current catalog requires code and policy-version changes when new actions are introduced. The
API does not yet issue signed, replay-resistant capabilities or persist authorization decisions;
those are required before a downstream service can trust the response in production.
