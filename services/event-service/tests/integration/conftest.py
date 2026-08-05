"""PostgreSQL integration fixture enabled only by an explicit test URL."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from app.config import reset_settings_cache
from app.infrastructure.database.repositories import PostgresEventRepository
from app.infrastructure.database.session import dispose_engine, get_engine


@pytest.fixture
def postgres_repo():
    url = os.getenv("EVENT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("EVENT_TEST_DATABASE_URL is not configured")
    os.environ["EVENT_DATABASE_URL"] = url
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
