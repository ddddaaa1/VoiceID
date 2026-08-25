# ADR 0016: Issue Short-lived, Device-bound, Single-use Grants

- Status: Accepted
- Date: 2026-08-25

## Context

An `allow` decision is evidence returned over an API connection, not a transferable permission. If
a downstream device accepts an unbound decision, an attacker can replay it, substitute another
action, or present it from another device. Persisting complete bearer tokens would also turn a
database read into immediate authorization.

## Decision

The durable deployment may issue an HMAC-SHA-256 signed capability only after an action decision is
`allow`. The grant binds a unique ID, authorization ID, identity, authenticated device, protected
action, caller nonce, issue time, and expiration. Its default lifetime is 30 seconds and cannot be
configured above five minutes.

Store only the token SHA-256 digest with its claims. Enforce a unique `(device_id, request_nonce)`
constraint and atomically set `consumed_at` under a write transaction. A grant can be consumed once,
by the same authenticated device, for the same action, before expiration. Return one generic error
for malformed, forged, expired, mismatched, unknown, and already-consumed grants.

The capability is signed but not encrypted. Claims contain only the identifiers and bindings needed
for authorization; callers must still treat the complete token as a bearer secret.

Authenticate reference devices with deployment-injected 256-bit opaque credentials. Keep grant
signing, template encryption, audit chaining, and device credentials as independent secrets.

## Consequences

Captured grants have a narrow time and action scope, replay is rejected by durable state, and a
database leak does not expose usable bearer tokens. Issuance and successful consumption also enter
the tamper-evident audit chain.

HMAC verification is centralized: every consumer needs access to VoiceID's atomic consumption API
rather than independently accepting the signature. Static device credentials are a reference
deployment mechanism, not a fleet identity solution. Production requires TLS, managed device
identity, credential rotation/revocation, clock monitoring, and rate limits at the trusted ingress.
