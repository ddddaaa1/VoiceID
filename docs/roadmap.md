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

## Current focus

Step 7 is complete. The first measured LibriSpeech clean report freezes its non-audio artifacts, real ECAPA scores, held-out metrics, Wilson intervals, and limitations. Its small correlated cohort does not justify replacing the provisional application threshold.

Step 8 is complete as a research evidence increment. The hash-locked, restart-safe runner scored
all 96,081 ASVspoof 2019 LA development/evaluation trials. Held-out class-1-logit EER is 0.829511%
and min t-DCF is 0.0275295, exactly matching the pinned upstream evaluator. Policy fusion remains
disabled because the development-selected softmax threshold accepted 6.296% of held-out spoof
trials and this single Logical Access corpus omits replay and modern deployment conditions.

Step 9 adds an AES-256-GCM encrypted, consent-gated SQLite reference deployment, transactional
revocation and retention, HMAC-linked audit records, and a single-node rate limiter. It also freezes
the PostgreSQL schema for scale-out and explicitly avoids raw-audio retention. Step 10 is now the
final delivered infrastructure increment.

Step 10 adds a hardened Docker/Compose deployment, GitHub Actions and dependency updates, a strict
hash-verified model release registry, pinned ECAPA lineage, Prometheus-compatible request metrics,
aggregate score-drift monitoring, and an immutable-image rollback runbook. All roadmap increments
are delivered on `main`; VoiceID remains an experimental portfolio system, not a production
biometric authenticator.
