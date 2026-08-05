"""Fixture dung chung cho integration test - can PostgreSQL that dang
chay (vi du qua `docker compose up postgres` hoac Laragon). Doc
EVENT_DATABASE_URL tu bien moi truong, mac dinh trung voi
root compose.yaml/.env.example."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.config import reset_settings_cache
from app.infrastructure.database.repositories import PostgresEventRepository
from app.infrastructure.database.session import dispose_engine, get_engine


@pytest.fixture
def postgres_repo():
    reset_settings_cache()
    dispose_engine()
    engine = get_engine()
    with engine.connect() as conn:
        # Xoa het du lieu, giu lai bang/sequence do migration tao - moi
        # test bat dau tu trang thai sach, khong phu thuoc thu tu chay.
        # TRUNCATE ca 2 bang cung luc (ticket_types co FK toi events).
        conn.execute(text("TRUNCATE TABLE event.ticket_types, event.events"))
        conn.execute(text("ALTER SEQUENCE event.event_id_seq RESTART WITH 1"))
        conn.commit()
    yield PostgresEventRepository()
    dispose_engine()
