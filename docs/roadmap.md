# VoiceID Delivery Roadmap

This roadmap describes the order in which VoiceID becomes a measurable speaker-verification product. A checked step means the implementation and its automated tests are present on `main`; it does not imply production readiness.

## Foundation

- [x] **Step 0 — Product and architecture definition**
  Define system boundaries, threat model, metrics, and the modular-monolith strategy.

- [x] **Step 1 — Audio preprocessing**
  Decode bounded PCM WAVE input, convert it to mono at 16 kHz, detect speech, and calculate quality signals.

- [x] **Step 2 — Speaker embeddings**
  Integrate ECAPA-TDNN behind a replaceable model port and validate real 192-dimensional embeddings.

## Core biometric workflow

- [x] **Step 3 — Multi-sample enrollment**
  Validate several recordings, reject outliers, build a versioned voice template, and persist it through a repository port.

- [x] **Step 4 — Speaker verification**
  Compare a new sample with an active template and return an auditable `accept`, `reject`, or `review` result.

- [x] **Step 5 — HTTP API**
  Expose identity enrollment and verification with explicit contracts, error responses, and request limits.

- [x] **Step 6 — Web integration**
  Replace the browser-only acoustic heuristic with the real backend workflow.

## Scientific evaluation and security

- [x] **Step 7 — Evaluation and calibration**
  Create versioned trial manifests, calculate FAR/FRR/EER/minDCF, and select thresholds without test-set leakage.

  - [x] **Step 7A — Scored-trial protocol and metric engine**
    Reject speaker leakage, select minDCF on development only, report held-out metrics, and break down evaluation results by condition.
  - [x] **Step 7B — Reproducible audio scoring runner**
    Generate scored trials from a consented PCM WAVE corpus with the versioned preprocessing and ECAPA adapters.
  - [x] **Step 7C — Measured calibration report**
    Freeze a real manifest, publish dataset limitations and confidence intervals, and replace the provisional threshold only if evidence supports it.

- [x] **Step 8 — Anti-spoofing**
  Define replay, synthetic-speech, and voice-conversion contracts; measure the Logical Access
  countermeasure and tandem system while keeping unmeasured replay outside the active policy.

  - [x] **Step 8A — Countermeasure protocol and metric engine**
    Freeze spoof-probability semantics, reject speaker leakage, calibrate on development only, and report held-out errors by attack category.
  - [x] **Step 8B — Pretrained countermeasure adapter**
    Integrate a versioned model behind `SpoofDetector`, document its preprocessing and provenance, and expose its model ID in every attempt.
  - [x] **Step 8C — ASVspoof and tandem evaluation**
    Score official protocols, calculate countermeasure EER and t-DCF, publish limitations, and enable fusion only if evidence supports it.
    - [x] Reproduce official ASVspoof 2021 LA baseline scores and validate EER/t-DCF.
    - [x] Score the open ODC-By corpus end to end with the VoiceID AASIST adapter.

## Product infrastructure

- [x] **Step 9 — Durable and secure persistence**
  Add encrypted durable templates, consent, retention, revocation, audit trails, and rate limits.
  Raw audio is deliberately not retained; PostgreSQL has a constraint-equivalent migration contract
  while the runnable reference deployment uses a persistent SQLite volume.

- [x] **Step 10 — MLOps and deployment**
  Add containers, CI, experiment tracking, a model registry, observability, drift monitoring, and rollback.

## Wearable product layer

- [x] **Step 11 — Risk-aware action authorization**
  Separate biometric evidence from product permission, assign risk on the server, expose
  `allow`/`deny`/`step_up` decisions, and demonstrate the policy in the web workflow.

- [x] **Step 12 — Replay-resistant authorization grants**
  Authenticate devices, bind action requests to nonces and short expirations, issue signed
  single-use capabilities, and persist authorization audit evidence.

- [ ] **Step 13 — Edge inference profile**
  Establish phone and ARM latency/memory/power budgets, export a quantized speaker model, and
  evaluate accuracy degradation across wearable microphones and noisy conditions.

  - [x] **Step 13A — Versioned full-waveform export**
    Export hash-bound FP32 and static INT8 QDQ ONNX graphs containing the acoustic frontend and
    ECAPA encoder; enforce PyTorch-to-ONNX fidelity before publishing provenance.
  - [x] **Step 13B — Local ARM64 benchmark**
    Measure artifact size, isolated single-thread graph latency, peak process RSS, embedding
    fidelity, and verification-score drift on the available Darwin ARM64 host.
  - [x] **Step 13C — Reproducible channel proxies**
    Evaluate clean enrollment against band-limited and noisy probes while explicitly keeping
    software transformations separate from wearable evidence.
  - [ ] **Step 13D — Phone and wearable hardware evidence**
    Measure latency, memory, energy, Bluetooth capture, and biometric degradation on phone-class
    ARM hardware with consented recordings from target wearable microphones.

- [ ] **Step 14 — Companion SDK prototype**
  Build a local-first mobile integration for Bluetooth microphones, device biometrics/passkeys,
  consent indicators, and action-policy callbacks.

  - [x] **Step 14A — Policy-preserving Swift API client**
    Model the server action catalog and decisions, use fresh secure nonces and Keychain credentials,
    issue signed grants, and consume them once without converting `step_up` into permission.
  - [x] **Step 14B — Bounded Bluetooth-capable capture boundary**
    Add user-initiated in-memory AVAudioEngine capture, iOS Bluetooth HFP routing, mono 16 kHz PCM
    output, and host-visible consent status callbacks.
  - [x] **Step 14C — Stronger-authentication integration boundary**
    Add LocalAuthentication and injectable passkey assertion protocols while documenting that local
    success is not a server-verifiable grant.
  - [ ] **Step 14D — Real companion app and verified step-up exchange**
    Build and test an iOS host app, add passkey challenge/completion and attestation on the server,
    integrate the ONNX runtime, and validate Bluetooth routes, interruptions, accessibility, and
    lifecycle behavior on real devices.
    - [x] Build a SwiftUI host with Keychain provisioning, visible bounded capture, server-policy
      presentation, one-time grant consumption, and UI-independent workflow tests.
    - [ ] Add and threat-model a server-verifiable passkey challenge/completion exchange.
    - [ ] Integrate the INT8 ONNX candidate and measure real phone/wearable behavior.

## Current focus

Step 7 is complete. The first measured LibriSpeech clean report freezes its non-audio artifacts, real ECAPA scores, held-out metrics, Wilson intervals, and limitations. Its small correlated cohort does not justify replacing the provisional application threshold.

Step 8 is complete as a research evidence increment. The hash-locked, restart-safe runner scored
all 96,081 ASVspoof 2019 LA development/evaluation trials. Held-out class-1-logit EER is 0.829511%
and min t-DCF is 0.0275295, exactly matching the pinned upstream evaluator. Policy fusion remains
disabled because the development-selected softmax threshold accepted 6.296% of held-out spoof
trials and this single Logical Access corpus omits replay and modern deployment conditions.

Step 9 adds an AES-256-GCM encrypted, consent-gated SQLite reference deployment, transactional
revocation and retention, HMAC-linked audit records, and a single-node rate limiter. It also freezes
the PostgreSQL schema for scale-out and explicitly avoids raw-audio retention.

Step 10 adds a hardened Docker/Compose deployment, GitHub Actions and dependency updates, a strict
hash-verified model release registry, pinned ECAPA lineage, Prometheus-compatible request metrics,
aggregate score-drift monitoring, and an immutable-image rollback runbook.

Step 11 begins the wearable product track. It introduces the server-owned
`wearable-action-risk-v1` catalog and preserves the complete verification lineage inside each
authorization decision.

Step 12 adds authenticated reference devices, canonical HMAC-signed 30-second grants, unique
request nonces, device/action binding, atomic one-time consumption, hash-only token persistence,
and chained audit evidence. Static device credentials are intentionally limited to the single-node
reference deployment.

Step 13A–13C add a full-waveform ONNX boundary, static INT8 QDQ export, hash-bound provenance,
isolated ARM64 measurements, and aggregate channel-proxy evidence. The 21.25 MiB candidate reduced
artifact size by about 73.5% and preserved high embedding fidelity, but it ran slower than FP32 on
this Mac. Noise proxies exposed substantial false-reject degradation. Step 13D and Step 14 remain
necessary for phone energy/performance, real wearable microphones, Bluetooth capture, and a real
companion integration. VoiceID remains an experimental portfolio system, not a production
biometric authenticator.

Step 14A–14C add a Swift package prototype with a typed authorization client, one-time grant
consumption, Keychain credential storage, bounded in-memory AVAudioEngine capture, consent events,
Bluetooth HFP routing, and explicit LocalAuthentication/passkey boundaries. Step 14D now has an
English SwiftUI host and a separately tested fail-closed workflow. It remains open until the server
verifies passkey assertions, ONNX inference runs on-device, and phone/wearable hardware evidence
covers routes, interruptions, lifecycle, accessibility, performance, energy, and accuracy.
