# ADR 0004: Expose a Versioned HTTP Boundary Without Coupling It to ML Frameworks

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

Enrollment and verification need a stable interface for the web client, automated evaluation, and future SDKs. Model inference is synchronous and CPU/GPU intensive, while FastAPI request handlers run in an asynchronous server. Uploaded audio is untrusted, potentially large binary input.

## Decision

Expose `/api/v1` endpoints using FastAPI and multipart `UploadFile` inputs. The adapter:

- injects application services through a container;
- keeps ECAPA loading lazy;
- performs bounded, chunked reads and closes every processed upload;
- limits file size, combined bytes, request bytes, media type, and file count;
- executes synchronous ML use cases in a worker thread rather than the event loop;
- maps expected failures to a stable error envelope;
- returns metadata and scores but never returns a voice embedding;
- publishes OpenAPI documentation from explicit Pydantic response schemas.

## Consequences

### Positive

- HTTP, ML, persistence, and domain logic remain independently testable.
- Contract tests run without model downloads by injecting stub services.
- The web application can integrate against a documented versioned boundary.
- Resource limits and privacy-sensitive response fields are explicit.

### Negative

- In-process inference cannot provide GPU backpressure or workload isolation.
- Application-level limits do not replace reverse-proxy limits.
- In-memory persistence prevents multi-process or durable operation.
- Authentication, authorization, rate limiting, and audit persistence remain future work.

The API remains a local research interface until those controls and calibrated biometric metrics are implemented.
