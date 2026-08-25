# ADR 0018: Preserve Server Policy in the Companion SDK

- Status: Accepted
- Date: 2026-08-26

## Context

A companion app must coordinate microphone capture, speaker verification, device credentials,
action policy, and stronger authentication. It is tempting to hide those states behind one Boolean
such as `isOwner`. That would collapse biometric evidence, product authorization, and device-local
authentication into an unsafe client decision.

Face ID or Touch ID success is meaningful to the local operating system, but a Boolean reported by
an app is not remotely verifiable. A passkey assertion requires a fresh server challenge plus
signature, relying-party, origin, and counter validation. VoiceID does not yet expose that exchange.

## Decision

Build the first companion boundary as a Swift package for iOS 17+ and macOS 14+. Keep server
responses explicit as `allow`, `deny`, or `step_up`. Return a signed grant only when the server
returned `allow` and included a grant. Never convert a local biometric result into a VoiceID grant.

Use a device-only Keychain item for the reference credential, a fresh secure random request nonce,
TLS except on loopback development, non-caching requests, and one-time server consumption. Provide
an injectable event callback so host products can render policy transitions without reclassifying
actions locally.

Capture only after an explicit call, bound duration to 0.5–10 seconds, publish status transitions
for a visible consent indicator, keep samples in memory, and emit mono 16 kHz PCM WAVE. On iOS,
allow Bluetooth HFP routing but report the actual selected route rather than assuming Bluetooth was
used.

Expose LocalAuthentication and passkey protocols as step-up integration points. Leave passkey
challenge/completion and device-attestation verification as an explicit server increment.

## Consequences

SDK consumers cannot mistake `step_up` for permission, and replay-resistant server grants retain
their authority. Capture and policy behavior are testable without a specific application UI.

The package alone is not a deployable iPhone app. Real-device microphone permission, interruptions,
route changes, Bluetooth codecs, app lifecycle, passkey verification, and the Step 13 ONNX runtime
still require an integration application and hardware evidence.
