BEGIN;

CREATE TABLE authorization_grants (
    grant_id TEXT PRIMARY KEY,
    authorization_id TEXT NOT NULL,
    identity_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    action TEXT NOT NULL,
    request_nonce TEXT NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL CHECK (expires_at > issued_at),
    token_sha256 CHAR(64) NOT NULL,
    consumed_at TIMESTAMPTZ,
    UNIQUE (device_id, request_nonce)
);

CREATE INDEX authorization_grants_expiration ON authorization_grants(expires_at);

COMMIT;
