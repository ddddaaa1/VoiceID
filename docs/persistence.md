# Durable Biometric Persistence

## Security model

The durable single-node adapter stores versioned templates, consent grants, revocation state,
authorization-grant state, and audit events in SQLite. Voice embeddings are serialized and
encrypted with AES-256-GCM before a
transaction reaches the database. Associated data binds each ciphertext to its identity, template,
version, model, and pipeline, so moving ciphertext between rows fails authentication.

Encryption, audit, and authorization-signing keys are supplied at process startup and are never
stored in the database.
Audit events form an HMAC-SHA-256 chain; changing an event, its order, or its predecessor breaks
verification. Database backups are still sensitive because identity identifiers, consent metadata,
and timestamps are not field-encrypted. Production must combine application encryption with
encrypted volumes, access controls, backup encryption, key rotation, and a managed KMS.

Raw enrollment and probe recordings are not retained. The API processes bounded multipart data and
discards it after the request, apart from temporary spooling performed by the HTTP stack. This data
minimization policy avoids creating a raw-biometric object store. A future evidence-retention use
case must introduce separate consent, encryption, access, and deletion controls before enabling an
object store.

## Run the durable application

Install the persistence extra and generate independent secrets for templates, audit chaining,
grant signing, and a reference device:

```bash
uv sync --extra ml --extra api --extra persistence --extra dev
export VOICEID_TEMPLATE_KEY="$(openssl rand -base64 32)"
export VOICEID_AUDIT_KEY="$(openssl rand -base64 32)"
export VOICEID_GRANT_KEY="$(openssl rand -base64 32)"
export VOICEID_DEMO_DEVICE_CREDENTIAL="$(openssl rand -base64 32)"
export VOICEID_DEVICE_CREDENTIALS="{\"wearable-demo\":\"${VOICEID_DEMO_DEVICE_CREDENTIAL}\"}"
export VOICEID_DATABASE_PATH="data/voiceid.sqlite3"
uv run uvicorn voiceid.adapters.api.durable_app:app --host 127.0.0.1 --port 8000
```

`VOICEID_DEVICE_CREDENTIALS` maps server-approved device IDs to base64-encoded 32-byte opaque
credentials. Environment variables are shown for local development. Do not put the secrets in `.env`, shell
history, container images, Compose files, or Git. Deployment should inject them from a secret
manager. Losing the template key makes existing embeddings unrecoverable; leaking it requires
rotation, reenrollment, and incident response.

Grant signing and device credentials require independent rotation plans. Rotating the grant key
invalidates unexpired tokens, which last only 30 seconds by default. Rotating a device credential
requires restarting this single-node reference process; there is no dynamic fleet registry.

## Authorization grant persistence

SQLite stores grant claims, a unique `(device_id, request_nonce)` pair, expiration, consumption time,
and only the SHA-256 digest of the signed token. The bearer token is returned once and is never
stored. `BEGIN IMMEDIATE` serializes issuance and consumption so concurrent requests cannot consume
the same grant twice. Issuance decisions and successful consumption are also appended to the HMAC
audit chain. Consumption also rechecks active biometric consent, so revocation or consent expiration
invalidates an otherwise unexpired grant. The retention purge removes expired or consumed grant
rows; their aggregate decision and consumption evidence remains in the chained audit log.

Schema version 2 migrates an existing version-1 database by adding the authorization-grant table
without modifying templates, consent, or audit history. PostgreSQL deployments apply
`002_authorization_grants.sql` after the original governance migration.

## Consent-first workflow

Durable enrollment and verification are consent-gated. Grant time-bounded consent before enrolling:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/identities/demo-user/consent \
  -H 'Content-Type: application/json' \
  -d '{
    "purpose": "speaker verification research demo",
    "notice_version": "privacy-v1",
    "expires_at": "2026-09-25T00:00:00Z"
  }'
```

Revoke consent and the active template atomically:

```bash
curl -X DELETE \
  'http://127.0.0.1:8000/api/v1/identities/demo-user?reason=user_request'
```

Revoked templates remain encrypted for the configured 30-day recovery/incident window and are
then eligible for purge. Consent expiration also makes enrollment and verification unavailable.
The default in-memory application remains available for disposable demos and clearly reports
`persistence=memory` in health responses.

## Concurrency and migration

The reference adapter opens short-lived SQLite connections, uses WAL, waits on busy locks, and uses
`BEGIN IMMEDIATE` for version changes, consent replacement, revocation, purge, and audit append.
It is appropriate for one API node with a persistent volume, not a multi-node service.

The PostgreSQL schema in `migrations/postgresql/001_biometric_governance.sql` preserves the same
constraints for a scale-out adapter. It is a migration contract, not a claim that the SQLite runtime
has magically become horizontally scalable. PostgreSQL integration and distributed rate limiting
remain deployment hardening work.

## Rate limits

Every non-GET `/api/v1/*` operation uses a thread-safe per-client fixed window in the single-node
process. The default is 60 requests per 60 seconds and returns `429` plus `Retry-After`. A reverse
proxy must enforce equivalent body and request limits, and a multi-node deployment must move the
counter to a trusted shared store. Proxy forwarding headers are intentionally not trusted by the
application unless an authenticated proxy boundary is added.
