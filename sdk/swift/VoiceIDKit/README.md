# VoiceIDKit

VoiceIDKit is the first companion SDK prototype for VoiceID. It targets iOS 17+ and macOS 14+
with Swift 6 and keeps four concerns separate:

- bounded, user-initiated `AVAudioEngine` capture with Bluetooth HFP routing on iOS;
- the authenticated authorization-grant and one-time consumption API;
- server-owned `allow`, `deny`, and `step_up` policy callbacks;
- device-owner authentication and an injectable passkey assertion boundary.

The package is a prototype integration boundary, not a production authentication SDK.

## Add the package

Add the local package directory in Xcode while developing:

```text
sdk/swift/VoiceIDKit
```

The host app needs `NSMicrophoneUsageDescription`. If it uses Face ID through
`LocalDeviceAuthenticator`, it also needs `NSFaceIDUsageDescription`. The app must show a persistent
visual capture indicator in addition to the operating system microphone indicator. Pass
`AVAudioEngineVoiceCommandCapture` status events into that UI.

## Configure credentials

Reference deployments authenticate a device with a static opaque credential. Store it in the
device-only Keychain adapter; never put it in source, `UserDefaults`, logs, URLs, or analytics.

```swift
let credentials = KeychainDeviceCredentialStore(account: "wearable-demo")
try await credentials.store(credentialFromProvisioning)

let configuration = try VoiceIDConfiguration(
    baseURL: URL(string: "https://voiceid.example")!,
    deviceID: "wearable-demo"
)
let client = VoiceIDHTTPClient(
    configuration: configuration,
    credentials: credentials
)
```

Plain HTTP is rejected except for `localhost` and `127.0.0.1` development servers.

## Capture and request a policy decision

```swift
let capture = AVAudioEngineVoiceCommandCapture { status in
    await captureIndicator.render(status)
}
let command = try await capture.capture(durationSeconds: 3)

let coordinator = AuthorizationCoordinator(client: client) { event in
    await productPolicyUI.render(event)
}
let resolution = try await coordinator.authorize(
    identityID: "demo-user",
    action: .readPrivateContent,
    pcmWave: command.pcmWave
)
```

Only `.granted` contains a signed server grant. A `.stepUpRequired` result is not permission to run
the action. `LocalDeviceAuthenticator` can prompt for Face ID, Touch ID, or device passcode, but its
local Boolean result is not server-verifiable evidence.

Production passkeys require a server challenge, an AuthenticationServices assertion in the host
app, and server-side signature/counter/origin validation. `PasskeyAssertionProviding` is the SDK
boundary for that future exchange; VoiceID does not yet expose the challenge/completion endpoints.

## Consume once

```swift
if case let .granted(grant) = resolution {
    let consumed = try await coordinator.consume(grant)
    try await protectedService.perform(consumed.action)
}
```

Consume immediately. Never persist or log `grant.token`. The server rejects replay, wrong-device,
wrong-action, expired, forged, and revoked grants with one intentionally generic error.

## Capture behavior

Capture is explicit and bounded to 0.5–10 seconds. The adapter requests the iOS recording category,
permits Bluetooth HFP input, records the active hardware format in memory, downmixes to mono,
linearly resamples to 16 kHz, emits 16-bit PCM WAVE, and then releases the audio session. It does
not retain a file and does not implement continuous listening.

AirPods and other HFP devices choose their real route and codec through iOS. The package does not
claim that a Bluetooth device was used merely because Bluetooth was allowed; the returned route
name and a real-device test must establish that fact.

## Current gaps

- The package has not run on an iPhone or target Bluetooth wearable.
- The local machine currently has mismatched Apple Command Line Tools (Swift 6.3.3 compiler with a
  Swift 6.3.2 SDK), so the first authoritative build must run in a coherent Xcode environment.
- The server has no passkey challenge/completion flow yet.
- The SDK calls the server inference path; wiring the Step 13 ONNX artifact into an on-device
  runtime remains a separate increment.
- Microphone permission UI, app lifecycle interruptions, route changes, background execution, and
  accessibility need host-app integration tests.
