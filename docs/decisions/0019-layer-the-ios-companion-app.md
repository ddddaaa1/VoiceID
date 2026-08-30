# ADR 0019: Layer the iOS companion app around a UI-independent workflow

- Status: accepted
- Date: 2026-08-31

## Context

VoiceIDKit established capture, HTTP, Keychain, one-time grant, and local-authentication boundaries,
but it did not prove that a real host application could compose them safely. A portfolio app also
needs useful presentation state without making policy decisions in SwiftUI or requiring a phone to
test the critical branches.

## Decision

Build the first host as an iOS 17 SwiftUI application and keep the Python service as the policy and
inference authority. Place the orchestration in a separate `VoiceIDCompanionCore` Swift package.
The package accepts protocol-based capture, grant-client, and device-owner-authentication adapters.

The workflow preserves three distinct outcomes:

- `allow`: validate the signed grant bindings and atomically consume it before reporting success;
- `deny`: block without grant consumption or local-authentication prompts;
- `step_up`: allow a local device-owner prompt, but keep the action blocked because that local
  result is not a server-verifiable assertion.

The host provisions the reference device credential into device-only Keychain storage, shows every
capture transition, reports the real input route, and never persists audio or displays grant tokens.

## Consequences

The security-sensitive state machine can run in macOS CI with deterministic fakes, while the Xcode
job verifies the actual iOS composition. The UI remains replaceable, and the same core could support
an OEM-branded application later.

This does not complete the production companion. A server passkey exchange, hardware-backed device
provisioning, on-device ONNX inference, and real phone/wearable validation remain explicit gates.
