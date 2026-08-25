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
        +---- low risk ----------> perform action
        +---- moderate/high -----> phone biometric or passkey when required
```

The first target is companion-device inference: AirPods, Bluetooth headsets, or glasses provide
audio while a phone runs the pipeline locally. Direct firmware deployment is a later OEM path and
requires a smaller quantized model plus hardware-specific integration.

## Trust boundary and limitations

- The action catalog and risk mapping are server-controlled and versioned as
  `wearable-action-risk-v1`.
- An `allow` response is scoped to the named action and must not be reused for another operation.
- The current endpoint does not issue a signed capability token or execute the downstream action.
- Authorization attempts are returned with the complete verification lineage but are not yet
  persisted as a dedicated audit record.
- A microphone cannot prove that the speaker is wearing the device. Nearby speech, replay, voice
  conversion, and synthetic audio remain relevant attacks.
- Production deployments require authenticated devices, challenge binding, short-lived signed
  authorization grants, replay protection, policy administration, and deployment-specific
  calibration.

## Extension strategy

OEM integrations should add actions through reviewed server policy rather than accepting arbitrary
client-provided risk. Device state can later add contextual signals such as trusted proximity,
lost-device mode, recent passkey authentication, command value, or anomalous location. Those
signals should refine policy without changing the raw biometric result.
