from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.application.service import BookingService
from app.config import Settings, reset_settings_cache
from app.infrastructure.database.session import get_engine, get_session_factory


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    url = os.getenv("BOOKING_TEST_DATABASE_URL")
    if not url:
        pytest.skip("BOOKING_TEST_DATABASE_URL is not configured")
    return Settings(
        app_name="booking-service",
        app_env="test",
        database_url=url,
        service_token="test-service-token",
        db_pool_size=10,
        db_max_overflow=10,
        db_pool_timeout_seconds=3,
        db_connect_timeout_seconds=3,
        db_lock_timeout_ms=3_000,
        db_statement_timeout_ms=10_000,
        idempotency_ttl_seconds=3_600,
        log_level="WARNING",
        docs_enabled=True,
    )


@pytest.fixture(scope="session", autouse=True)
def migrated_database(test_settings: Settings) -> Iterator[None]:
    root = Path(__file__).resolve().parents[2]
    previous_url = os.getenv("BOOKING_DATABASE_URL")
    os.environ["BOOKING_DATABASE_URL"] = test_settings.database_url
    reset_settings_cache()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    try:
        command.upgrade(config, "head")
        yield
    finally:
        if previous_url is None:
            os.environ.pop("BOOKING_DATABASE_URL", None)
        else:
            os.environ["BOOKING_DATABASE_URL"] = previous_url
        reset_settings_cache()


@pytest.fixture(autouse=True)
def clean_database(test_settings: Settings) -> Iterator[None]:
    engine = get_engine(test_settings)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE booking.outbox_events, booking.booking_audit, "
                "booking.idempotency_records, booking.booking_items, "
                "booking.bookings CASCADE"
            )
        )
    yield


@pytest.fixture
def service(test_settings: Settings) -> BookingService:
    return BookingService(test_settings, get_session_factory(test_settings))
