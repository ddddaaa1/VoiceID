# Risk-aware Action Authorization

VoiceID turns speaker-verification evidence into a product decision for screenless devices. The
authorization layer is intentionally separate from the biometric model: a voice match answers
whether a probe resembles an enrolled speaker, while an action policy decides whether that
evidence is sufficient for a requested operation.

## Public action catalog

Clients submit a named action, never a caller-selected risk level. The server owns this mapping so
a compromised wearable or SDK consumer cannot label a purchase as low risk.

| Action | Risk | Accepted voice without spoof evidence | Accepted voice with spoof evidence |
|---|---|---|---|
| `play_media` | Low | Allow | Allow |
| `personalize_assistant` | Low | Allow | Allow |
| `switch_profile` | Moderate | Step up | Allow |
| `read_private_content` | Moderate | Step up | Allow |
| `send_message` | High | Step up | Step up |
| `make_purchase` | High | Step up | Step up |
| `unlock_physical_access` | High | Step up | Step up |

A rejected speaker decision denies the action. An inconclusive speaker decision requests stronger
authentication instead of treating poor audio as proof of an impostor. High-risk actions always
require a device biometric or passkey; voice is only a risk-reduction signal for those operations.

The default API currently has anti-spoofing disabled. Consequently, moderate-risk actions request
step-up authentication even after an accepted speaker match. This is expected policy behavior, not
an integration failure.

## Wearable deployment shape

```text
Wearable microphone
        |
        v
Companion app: capture + consent indicator
        |
        v
VoiceID: quality -> speaker match -> optional spoof check
        |
        v
Action policy: allow | deny | step_up
        |
        +---- allow -> signed 30-second grant -> consume once -> perform action
        +---- moderate/high -----> phone biometric or passkey when required
```

The first target is companion-device inference: AirPods, Bluetooth headsets, or glasses provide
audio while a phone runs the pipeline locally. Direct firmware deployment is a later OEM path and
requires a smaller quantized model plus hardware-specific integration.

## Trust boundary and limitations

- The action catalog and risk mapping are server-controlled and versioned as
  `wearable-action-risk-v1`.
- An `allow` response is scoped to the named action and must not be reused for another operation.
- Durable mode can exchange an `allow` decision for an HMAC-signed, device-bound grant. The grant
  has a unique caller nonce, expires after 30 seconds, and is atomically consumed once.
- SQLite stores the grant claims and token SHA-256 digest, never the bearer token. Decisions and
  successful consumption enter the tamper-evident audit chain.
- Identity revocation or consent expiration makes an otherwise unexpired grant unavailable.
- The policy-only `/authorize` endpoint still executes no downstream action and produces no grant.
- A microphone cannot prove that the speaker is wearing the device. Nearby speech, replay, voice
  conversion, and synthetic audio remain relevant attacks.
- The reference device credential registry is static and deployment-injected. Production fleets
  still require managed device identity, credential rotation/revocation, TLS, policy administration,
  and deployment-specific biometric calibration.

## Extension strategy

OEM integrations should add actions through reviewed server policy rather than accepting arbitrary
client-provided risk. Device state can later add contextual signals such as trusted proximity,
lost-device mode, recent passkey authentication, command value, or anomalous location. Those
signals should refine policy without changing the raw biometric result.

## Companion SDK prototype

[`VoiceIDKit`](../sdk/swift/VoiceIDKit/README.md) models this boundary for Apple companion apps. It
keeps server decisions typed, obtains signed grants only for `allow`, emits product callbacks for
all three policy outcomes, and consumes grants once. Its AVAudioEngine adapter performs explicit,
bounded, in-memory capture and permits Bluetooth HFP input on iOS.

`LocalDeviceAuthenticator` can present the operating system's device-owner authentication UI, but
that local result does not complete a VoiceID `step_up`. A production passkey path still needs a
server challenge and server-side assertion validation before a new grant can be issued.
