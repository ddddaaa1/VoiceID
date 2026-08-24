BEGIN;

CREATE TABLE voice_templates (
    template_id TEXT PRIMARY KEY,
    identity_id TEXT NOT NULL,
    embedding_nonce BYTEA NOT NULL,
    embedding_ciphertext BYTEA NOT NULL,
    model_id TEXT NOT NULL,
    pipeline_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    sample_count INTEGER NOT NULL CHECK (sample_count > 0),
    created_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    revocation_reason TEXT,
    UNIQUE (identity_id, version)
);

CREATE UNIQUE INDEX one_active_template_per_identity
ON voice_templates(identity_id) WHERE revoked_at IS NULL;

CREATE TABLE consents (
    consent_id TEXT PRIMARY KEY,
    identity_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    notice_version TEXT NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL CHECK (expires_at > granted_at),
    revoked_at TIMESTAMPTZ,
    revocation_reason TEXT
);

CREATE UNIQUE INDEX one_active_consent_per_identity
ON consents(identity_id) WHERE revoked_at IS NULL;

CREATE TABLE audit_events (
    sequence BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    identity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    outcome TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    details_json JSONB NOT NULL,
    previous_hash CHAR(64) NOT NULL,
    event_hash CHAR(64) NOT NULL UNIQUE
);

COMMIT;
