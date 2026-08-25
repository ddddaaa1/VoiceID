# MLOps, Observability, and Deployment

## Reproducible release boundary

The lockfile pins Python dependencies and hashes, and resolves Torch/Torchaudio from PyTorch's
explicit CPU-only index so Linux cannot silently pull CUDA libraries. The container pins its Python and `uv` toolchain,
runs as an unprivileged user, drops Linux capabilities, uses a read-only root filesystem, and writes
only to bounded temporary storage plus explicit data/model volumes. Compose binds to localhost by
default because the research API does not yet implement user authentication.

The model release in `model-registry/releases/voiceid-research-2026-08-25.json` binds runtime model
IDs to immutable upstream revisions, artifact hashes, evaluation evidence, and deployment state.
`scripts/verify_model_release.py` rejects unknown fields, path traversal, hash changes, adapter ID
drift, duplicate roles, and accidental anti-spoof enablement. AASIST remains registered but disabled
despite its newly registered end-to-end evidence: the development-selected threshold did not
transfer safely to held-out attacks, and a single 2019 Logical Access corpus does not support a
deployment fusion policy.

Experiment tracking is intentionally file-based at this stage: each directory under `experiments/`
freezes manifests, hashes, scores, reports, lineage, and interpretation in Git. This is reviewable in
a public portfolio and requires no external tracking service. The boundaries allow those artifacts
to be mirrored to MLflow later, but this repository does not claim an MLflow server or registry is
running.

The ASVspoof end-to-end experiment applies a narrower public boundary: aggregate reports,
acquisition provenance, and artifact-level hashes are committed, while per-audio hashes and
per-trial model outputs remain local and ignored. The committed runner can regenerate them from the
official corpus. This preserves portfolio reviewability without treating biometric-derived rows as
ordinary repository data.

The ECAPA adapter now pins Hugging Face revision
`0f99f2d0ebe89ac095bcc5903c4dd8f72b367286` and disables update checks. First inference still needs
network access unless the persistent model volume is already populated. For an offline deployment,
populate and verify that volume during an image promotion process rather than allowing production
nodes to resolve mutable remote content.

## Continuous integration

GitHub Actions runs Ruff lint and format checks, 100+ Python tests with warnings promoted to errors,
browser WAVE tests, model-release integrity verification, the frozen drift smoke check, and an
offline package build from the synchronized environment. Main-branch
pushes also build the Docker image and validate Compose. Dependabot covers Python, Actions, and the
base image. CI builds an image but does not publish or deploy it, so a repository push cannot mutate
an external environment.

## Metrics and request correlation

`GET /metrics` exposes Prometheus text metrics for request counts and latency histograms. Identity
path values and asset names are normalized before becoming labels, preventing biometric identifiers
and unbounded cardinality from entering telemetry. Responses include an `X-Request-ID`; a syntactically
safe caller value is propagated, otherwise the API generates one.

The endpoint must be restricted to an internal network by ingress policy. Metrics deliberately omit
raw audio, embeddings, identity IDs, and individual scores. Recommended alerts include sustained 5xx
rates, p95 latency, rate-limit responses, health failures, disk capacity, audit-chain verification,
and retention-job failures.

## Drift monitoring

`scripts/monitor_score_drift.py` calculates Population Stability Index against a frozen histogram and
returns `stable`, `warning`, or `alert`. It requires at least 30 finite scores, rejects model mismatch,
and stores only aggregate proportions in its output. The bundled LibriSpeech baseline is a pipeline
smoke fixture with only 60 held-out scores; it is not a production reference population.

Any model revision needs a new baseline. Drift is an investigation trigger, not proof of degraded
accuracy: changing prevalence, devices, languages, quality gates, or attacks can all move a score
distribution. Labeled evaluation remains necessary before threshold or model changes.

## Build and run

```bash
docker build -t voiceid:local .
export VOICEID_TEMPLATE_KEY="$(openssl rand -base64 32)"
export VOICEID_AUDIT_KEY="$(openssl rand -base64 32)"
export VOICEID_GRANT_KEY="$(openssl rand -base64 32)"
export VOICEID_DEMO_DEVICE_CREDENTIAL="$(openssl rand -base64 32)"
export VOICEID_DEVICE_CREDENTIALS="{\"wearable-demo\":\"${VOICEID_DEMO_DEVICE_CREDENTIAL}\"}"
docker compose up --build
```

Open `http://127.0.0.1:8000`. The named `voiceid-data` volume preserves the encrypted database; the
`voiceid-models` volume preserves downloaded ECAPA files. Back up the data volume only together with
a tested secret-recovery process. Never commit or bake the keys into an image.

## Promotion and rollback

1. Run CI and verify the model release manifest.
2. Build an immutable image tagged with the Git commit SHA and record its digest.
3. Back up the encrypted database and verify the audit chain and secret recovery.
4. Deploy one canary, exercise health and a consented synthetic workflow, and observe latency/errors.
5. Promote the same digest; never rebuild an already approved tag.

Rollback changes the `VOICEID_IMAGE` value to the previously recorded digest and recreates the API
without deleting volumes. Database migrations must remain backward compatible for at least one
release. If a migration is not backward compatible, restore a pre-migration encrypted backup in a
separate recovery environment; do not run destructive downgrade SQL in place. A model rollback may
make newer templates incompatible by design, resulting in explicit `speaker_model_mismatch` rather
than silent cross-version comparison.

This procedure is documented and CI-verifiable, but no cloud environment is mutated by this repo.
External deployment still needs TLS, authentication, ingress request limits, secret management,
centralized logs/metrics, vulnerability scanning, backups, and incident response.
