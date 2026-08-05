"""Fixture dung chung cho integration test - can PostgreSQL that dang
chay (vi du qua `docker compose up postgres`). Doc NOTIFICATION_DATABASE_URL
tu bien moi truong, mac dinh trung voi root compose.yaml/.env.example
cua service nay."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.config import reset_settings_cache
from app.infrastructure.database.repositories import PostgresDeliveryRepository
from app.infrastructure.database.session import dispose_engine, get_engine


@pytest.fixture
def postgres_repo():
    reset_settings_cache()
    dispose_engine()
    engine = get_engine()
    with engine.connect() as conn:
        # Xoa het du lieu, giu lai bang/sequence do migration tao - moi
        # test bat dau tu trang thai sach, khong phu thuoc thu tu chay.
        conn.execute(text("TRUNCATE TABLE notification.deliveries"))
        conn.execute(text("ALTER SEQUENCE notification.delivery_id_seq RESTART WITH 1"))
        conn.commit()
    yield PostgresDeliveryRepository()
    dispose_engine()
