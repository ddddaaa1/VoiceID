# VoiceID HTTP API v1

The API exposes the research enrollment and verification workflow through versioned multipart endpoints. It also serves the same-origin web client at `/`; interactive OpenAPI documentation is available at `/docs`.

## Start the server

```bash
uv sync --extra ml --extra api --extra persistence --extra dev
uv run uvicorn voiceid.adapters.api.app:app --host 127.0.0.1 --port 8000
```

The default process uses in-memory template persistence. Restarting the process removes every
enrolled identity. The [durable deployment guide](persistence.md) describes the consent-gated,
AES-256-GCM encrypted SQLite mode and its key-management requirements.

## Web client

```http
GET /
```

The HTML client and its `/assets/*` modules are served by the API process. Keeping the UI and API on the same origin avoids a broader CORS policy and makes the browser's security boundary explicit. Static responses include a restrictive Content Security Policy and permit microphone access only to the same origin.

## Health

```http
GET /api/v1/health
```

The response identifies the speaker model, decision policy, persistence adapter, and anti-spoofing availability. Calling this endpoint does not load ECAPA model weights.

## Enroll an identity

```bash
curl -X POST http://127.0.0.1:8000/api/v1/identities/demo-user/enroll \
  -F 'samples=@sample-1.wav;type=audio/wav' \
  -F 'samples=@sample-2.wav;type=audio/wav' \
  -F 'samples=@sample-3.wav;type=audio/wav'
```

Successful enrollment returns `201 Created` with template metadata and any discarded sample indices. The response never contains the voice embedding.

Durable mode first requires `POST /api/v1/identities/{identity_id}/consent` with a purpose, privacy
notice version, and expiration. `DELETE /api/v1/identities/{identity_id}?reason=user_request`
atomically revokes active consent and templates.

## Verify an identity

```bash
curl -X POST http://127.0.0.1:8000/api/v1/identities/demo-user/verify \
  -F 'sample=@probe.wav;type=audio/wav'
```

Example response:

```json
{
  "attempt_id": "c270f0df-88ea-4f54-955d-e87fcba80235",
  "created_at": "2026-08-24T15:00:00Z",
  "identity_id": "demo-user",
  "template_id": "f9e5f1e0-6195-4021-bf73-e1ece0cb2b2a",
  "template_version": 1,
  "model_id": "speechbrain/spkrec-ecapa-voxceleb@0f99f2d0ebe89ac095bcc5903c4dd8f72b367286",
  "pipeline_id": "pcm-wave-linear-energy-vad-v1",
  "policy_id": "provisional-cosine-v1",
  "decision": "accept",
  "speaker_score": 0.84,
  "spoof_probability": null,
  "spoof_model_id": null,
  "reasons": ["speaker_match", "spoof_check_not_run"]
}
```

The example is a contract illustration, not a measured result or recommended threshold.

## Authorize a protected action

```bash
curl -X POST http://127.0.0.1:8000/api/v1/identities/demo-user/authorize \
  -F 'action=read_private_content' \
  -F 'sample=@probe.wav;type=audio/wav'
```

The response contains an action-level `allow`, `deny`, or `step_up` decision and nests the complete
speaker-verification response used as evidence. Clients choose a named action from the public enum;
the server assigns its risk level.

```json
{
  "authorization_id": "8e8055b0-02eb-4e96-bac8-51236117f7f1",
  "created_at": "2026-08-25T12:00:00Z",
  "identity_id": "demo-user",
  "action": "read_private_content",
  "risk": "moderate",
  "decision": "step_up",
  "authorization_policy_id": "wearable-action-risk-v1",
  "reasons": ["spoof_evidence_required", "device_authentication_required"],
  "verification": {
    "attempt_id": "c270f0df-88ea-4f54-955d-e87fcba80235",
    "created_at": "2026-08-25T12:00:00Z",
    "identity_id": "demo-user",
    "template_id": "f9e5f1e0-6195-4021-bf73-e1ece0cb2b2a",
    "template_version": 1,
    "model_id": "speechbrain/spkrec-ecapa-voxceleb@0f99f2d0ebe89ac095bcc5903c4dd8f72b367286",
    "spoof_model_id": null,
    "pipeline_id": "pcm-wave-linear-energy-vad-v1",
    "policy_id": "provisional-cosine-v1",
    "decision": "accept",
    "speaker_score": 0.84,
    "spoof_probability": null,
    "reasons": ["speaker_match", "spoof_check_not_run"]
  }
}
```

See [risk-aware action authorization](action-authorization.md) for the action catalog and safety
rules. The endpoint returns a policy decision; it does not execute the action or issue a signed
authorization capability. Durable clients use the grant endpoints below when an actionable,
replay-resistant permission is required.

## Issue a signed authorization grant

Signed grants are available only in durable mode and require an authenticated device. Generate a
fresh cryptographically random nonce for every request; never derive it from an identity or reuse it
after any successful issuance.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/identities/demo-user/authorization-grants \
  -H 'X-VoiceID-Device-ID: wearable-demo' \
  -H "Authorization: Device ${VOICEID_DEMO_DEVICE_CREDENTIAL}" \
  -F 'action=play_media' \
  -F "request_nonce=$(openssl rand -hex 16)" \
  -F 'sample=@probe.wav;type=audio/wav'
```

The response always includes the complete `ActionAuthorizationResponse` as `authorization`.
`grant` is `null` for `deny` and `step_up`; only `allow` can issue a token. The grant portion of an
allow response is:

```json
{
  "grant": {
    "grant_id": "grant-1",
    "authorization_id": "authorization-1",
    "identity_id": "demo-user",
    "device_id": "wearable-demo",
    "action": "play_media",
    "issued_at": "2026-08-25T12:00:00Z",
    "expires_at": "2026-08-25T12:00:30Z",
    "token": "base64url-claims.base64url-signature"
  }
}
```

## Consume a grant

The same authenticated device submits the token and exact protected action before expiration:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/authorization-grants/consume \
  -H 'Content-Type: application/json' \
  -H 'X-VoiceID-Device-ID: wearable-demo' \
  -H "Authorization: Device ${VOICEID_DEMO_DEVICE_CREDENTIAL}" \
  -d '{"token":"base64url-claims.base64url-signature","action":"play_media"}'
```

Consumption atomically marks the grant used. Repeating it returns
`grant_invalid_or_unavailable`, the same error used for malformed, forged, expired, mismatched, or
unknown grants. This intentionally avoids exposing token state. Treat the token as a secret: do not
place it in URLs, logs, analytics, or client persistence.

The token is signed, not encrypted. Its identity, device, action, nonce, and timestamps are encoded
claims and must not contain additional confidential data.

All `/api/v1/*` responses include `Cache-Control: no-store`; clients and trusted proxies must not
override this for biometric evidence or grant tokens.

## Error envelope

All expected API, validation, enrollment, and verification failures use the same top-level shape:

```json
{
  "error": {
    "code": "insufficient_valid_samples",
    "message": "The enrollment request could not produce a valid voice template.",
    "details": [
      {"sample_index": 1, "reasons": ["low_snr"]}
    ]
  }
}
```

Clients should branch on `error.code`, not the human-readable message.

## Current upload limits

| Limit | Value |
|---|---:|
| Maximum file size | 10 MB |
| Maximum combined file bytes | 40 MB |
| Maximum request body | 42 MB |
| Maximum enrollment files | 8 |

The application enforces limits while reading spooled uploads and checks `Content-Length` when present. A deployed service must also configure an equivalent limit at the reverse proxy or ingress layer.

## Current constraints

- Accepted inputs are bounded 16-bit PCM WAVE files.
- General identity endpoints do not implement end-user authentication. Signed-grant endpoints in
  durable mode authenticate a reference device credential, but a trusted TLS ingress and managed
  device identity are still required for production.
- Templates are stored only in process memory.
- Raw audio is not intentionally persisted, although the multipart implementation may spool request data to temporary storage while handling a request.
- `provisional-cosine-v1` has not been calibrated against VoiceID evaluation data.
- An audited AASIST adapter and end-to-end ASVspoof evidence are packaged, but anti-spoofing remains
  disabled because the development-calibrated threshold did not transfer safely to held-out
  attacks. Its absence is included in the result reasons and `spoof_model_id` remains `null` when
  no countermeasure runs.
- The API never executes the protected downstream action. The consuming service must treat a
  successful one-time consumption response as scoped only to its returned device, identity, and
  action.
