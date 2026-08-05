"""PostgreSQL integration fixture enabled only by an explicit test URL."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from app.config import reset_settings_cache
from app.infrastructure.database.repositories import PostgresCustomerRepository
from app.infrastructure.database.session import dispose_engine, get_engine


@pytest.fixture
def postgres_repo():
    url = os.getenv("CUSTOMER_TEST_DATABASE_URL")
    if not url:
        pytest.skip("CUSTOMER_TEST_DATABASE_URL is not configured")
    os.environ["CUSTOMER_DATABASE_URL"] = url
    reset_settings_cache()
    dispose_engine()
    engine = get_engine()
    with engine.connect() as conn:
        # Xoa het du lieu, giu lai bang/sequence do migration tao - moi
        # test bat dau tu trang thai sach, khong phu thuoc thu tu chay.
        conn.execute(text("TRUNCATE TABLE customer.customers"))
        conn.execute(text("ALTER SEQUENCE customer.customer_id_seq RESTART WITH 1"))
        conn.commit()
    yield PostgresCustomerRepository()
    dispose_engine()
