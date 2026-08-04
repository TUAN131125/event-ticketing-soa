"""Fixture dung chung cho integration test - can PostgreSQL that dang
chay. Doc EVENT_DATABASE_URL tu bien moi truong."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.config import reset_settings_cache
from app.infrastructure.database.repositories import (
    PostgresAuditRepository,
    PostgresEventRepository,
    PostgresIdempotencyRepository,
)
from app.infrastructure.database.session import dispose_engine, get_engine


@pytest.fixture
def postgres_repo():
    reset_settings_cache()
    dispose_engine()
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text(
            "TRUNCATE TABLE event.idempotency_keys, event.event_audit, "
            "event.ticket_types, event.events"
        ))
        conn.execute(text("ALTER SEQUENCE event.event_id_seq RESTART WITH 1"))
        conn.commit()
    yield PostgresEventRepository()
    dispose_engine()


@pytest.fixture
def postgres_audit_repo(postgres_repo):
    return PostgresAuditRepository()


@pytest.fixture
def postgres_idem_repo(postgres_repo):
    return PostgresIdempotencyRepository()
