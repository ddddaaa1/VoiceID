# VoiceID HTTP API v1

The API exposes the research enrollment and verification workflow through versioned multipart endpoints. Interactive OpenAPI documentation is available at `/docs` while the server is running.

## Start the server

```bash
uv sync --extra ml --extra api --extra dev
uv run uvicorn voiceid.adapters.api.app:app --host 127.0.0.1 --port 8000
```

The default process uses in-memory template persistence. Restarting the process removes every enrolled identity.

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
  "model_id": "speechbrain/spkrec-ecapa-voxceleb",
  "pipeline_id": "pcm-wave-linear-energy-vad-v1",
  "policy_id": "provisional-cosine-v1",
  "decision": "accept",
  "speaker_score": 0.84,
  "spoof_probability": null,
  "reasons": ["speaker_match", "spoof_check_not_run"]
}
```

The example is a contract illustration, not a measured result or recommended threshold.

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
- There is no authentication or rate limiting yet.
- Templates are stored only in process memory.
- Raw audio is not intentionally persisted, although the multipart implementation may spool request data to temporary storage while handling a request.
- `provisional-cosine-v1` has not been calibrated against VoiceID evaluation data.
- Anti-spoofing is not enabled and this absence is included in the result reasons.
