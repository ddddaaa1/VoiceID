# VoiceID Companion for iOS

This SwiftUI application is the first runnable host for `VoiceIDKit`. It demonstrates a bounded
microphone capture, an authenticated request to the durable VoiceID API, server-owned action policy,
single-use grant consumption, and a fail-closed local device-authentication boundary.

The interface and all client-facing copy are in English for portfolio and customer review.

## Architecture

```text
SwiftUI view
    -> CompanionViewModel (presentation and Keychain provisioning)
    -> VoiceIDCompanionCore (tested allow / deny / step-up workflow)
    -> VoiceIDKit (audio capture, HTTP, Keychain, LocalAuthentication)
    -> durable Python API (verification, policy, signed one-time grants)
```

`VoiceIDCompanionCore` has no UI dependency. Its tests use fake capture, network, and biometric
adapters to prove that:

- `allow` consumes the device-bound grant exactly once;
- `deny` never consumes a grant or requests local authentication;
- `step_up` may confirm the device owner locally but never becomes permission without a future
  server-verifiable exchange.

No raw recording or grant token is written to disk or displayed. The static development device
credential is stored with `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` in Keychain.

## Open and build

Open `VoiceIDCompanion.xcodeproj` in Xcode 16 or newer. The project uses local Swift packages, so no
package account or remote dependency is required.

The committed project is generated from `project.yml` with XcodeGen 2.46.0. After changing the
project specification, regenerate it with:

```bash
xcodegen generate --spec apps/ios/VoiceIDCompanion/project.yml
```

Run package logic tests independently:

```bash
cd apps/ios/VoiceIDCompanion/CompanionCore
swift test
```

## Connect to the API

The grant endpoints exist only in the durable application. Configure it as described in
`docs/persistence.md`, grant consent, and enroll `demo-user` before using the app.

For the iOS Simulator, start the API on the Mac at `127.0.0.1:8000`, leave the default app URL, and
save the same `wearable-demo` credential that was injected into
`VOICEID_DEVICE_CREDENTIALS`. The credential field is cleared immediately after a successful
Keychain save.

A physical iPhone cannot use the Mac's loopback address. Use an HTTPS development endpoint that is
reachable from the phone; the client intentionally rejects clear-text non-loopback URLs.

## What is intentionally incomplete

- Local Face ID, Touch ID, or passcode success is not server-verifiable. A passkey
  challenge/assertion/completion protocol is still required before a `step_up` action can execute.
- The app calls server-side inference. The INT8 ONNX model is not yet wired into an iOS runtime.
- Bluetooth route, interruptions, energy, latency, accessibility, and biometric accuracy still
  require tests on real phones and target wearables.
- The current device credential is a static single-node development mechanism, not fleet
  provisioning or hardware-backed device attestation.

This remains an experimental portfolio application, not a production identity authenticator.
