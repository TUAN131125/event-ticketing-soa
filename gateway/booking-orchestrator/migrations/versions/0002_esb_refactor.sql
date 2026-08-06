-- Canonical PostgreSQL schema used by app.persistence.repositories.PostgresRepository.
-- Run this migration before starting the ESB. The application never creates production
-- tables implicitly.
CREATE TABLE IF NOT EXISTS esb_workflows_v2 (
    workflow_id VARCHAR(64) PRIMARY KEY,
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    correlation_id VARCHAR(128),
    status VARCHAR(40) NOT NULL,
    body JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_esb_workflows_v2_correlation_id
    ON esb_workflows_v2(correlation_id);
CREATE INDEX IF NOT EXISTS ix_esb_workflows_v2_status
    ON esb_workflows_v2(status);

CREATE TABLE IF NOT EXISTS esb_outbox_v2 (
    message_id VARCHAR(64) PRIMARY KEY,
    state VARCHAR(32) NOT NULL,
    next_attempt_at DOUBLE PRECISION NOT NULL,
    body JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_esb_outbox_v2_due
    ON esb_outbox_v2(state, next_attempt_at);

CREATE TABLE IF NOT EXISTS esb_ws_ticket_v2 (
    cache_key VARCHAR(256) PRIMARY KEY,
    expires_at BIGINT NOT NULL,
    body JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_esb_ws_ticket_v2_expires_at
    ON esb_ws_ticket_v2(expires_at);
