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

- [ ] **Step 4 — Speaker verification**  
  Compare a new sample with an active template and return an auditable `accept`, `reject`, or `review` result.

- [ ] **Step 5 — HTTP API**  
  Expose identity enrollment and verification with explicit contracts, error responses, and request limits.

- [ ] **Step 6 — Web integration**  
  Replace the browser-only acoustic heuristic with the real backend workflow.

## Scientific evaluation and security

- [ ] **Step 7 — Evaluation and calibration**  
  Create versioned trial manifests, calculate FAR/FRR/EER/minDCF, and select thresholds without test-set leakage.

- [ ] **Step 8 — Anti-spoofing**  
  Detect replay, synthetic speech, and voice conversion; evaluate the tandem system with ASVspoof protocols.

## Product infrastructure

- [ ] **Step 9 — Durable and secure persistence**  
  Add PostgreSQL, encrypted object storage, consent, retention, revocation, audit trails, and rate limits.

- [ ] **Step 10 — MLOps and deployment**  
  Add containers, CI, experiment tracking, a model registry, observability, drift monitoring, and rollback.

## Current focus

Step 3 is complete. The next increment is Step 4: speaker verification using the active template created during enrollment.
