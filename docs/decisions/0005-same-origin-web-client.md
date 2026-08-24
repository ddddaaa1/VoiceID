# ADR 0005: Serve a same-origin web client with client-side PCM capture

- **Status:** Accepted
- **Date:** 2026-08-25

## Context

The initial visual prototype calculated a browser-only acoustic heuristic. That behavior could not exercise the real preprocessing, ECAPA embedding, enrollment, or verification logic and risked presenting an unrelated percentage as a biometric result.

The first integrated client should remain small, inspectable, and easy to run locally. Introducing a separate frontend server, CORS policy, build pipeline, and framework would add operational surface without improving the current research workflow.

## Decision

FastAPI serves a dependency-free ES module client and its static assets from the same origin as `/api/v1`. The browser captures microphone frames with an `AudioWorklet`, encodes mono 16-bit PCM WAVE payloads, and sends three enrollment files or one verification file through the public multipart contracts.

The client displays the raw API score, policy, decision, and reason codes. It does not reproduce scoring or threshold logic. Static responses receive a restrictive Content Security Policy and same-origin microphone permissions policy.

## Consequences

- Local startup is one process and no permissive CORS configuration is necessary.
- The user interface tests the same public API available to other clients.
- WAVE encoding is independently testable without microphone hardware.
- The browser's input sample rate may vary; canonical resampling remains a backend responsibility.
- A future TypeScript or React client can replace this adapter without changing application or domain layers.
- Microphone automation requires an explicit permission decision, so browser QA does not grant it implicitly.
