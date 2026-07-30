"""Shared real-PostgreSQL fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.application.common import RequestContext
from app.application.configure_inventory import SeatDefinition, configure_inventory
from app.config import Settings, reset_settings_cache
from app.domain.seat import SeatStatus
from app.infrastructure.database.session import (
    dispose_engine,
    get_engine,
    session_scope,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://seat_inventory:seat_inventory"
    "@localhost:55432/seat_inventory_test"
)


@pytest.fixture(scope="session")
def test_settings() -> Iterator[Settings]:
    os.environ["SEAT_DATABASE_URL"] = os.getenv(
        "SEAT_TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL
    )
    os.environ["SEAT_SERVICE_TOKEN"] = "test-service-token"
    os.environ["SEAT_SOAP_PUBLIC_URL"] = "http://testserver/soap"
    os.environ["SEAT_MIN_HOLD_SECONDS"] = "1"
    os.environ["SEAT_DEFAULT_HOLD_SECONDS"] = "2"
    os.environ["SEAT_MAX_HOLD_SECONDS"] = "30"
    os.environ["SEAT_MAX_EXTENSION_SECONDS"] = "5"
    os.environ["SEAT_DB_LOCK_TIMEOUT_MS"] = "250"
    os.environ["SEAT_DB_STATEMENT_TIMEOUT_MS"] = "5000"
    os.environ["SEAT_DB_POOL_SIZE"] = "40"
    os.environ["SEAT_DB_MAX_OVERFLOW"] = "30"
    os.environ["SEAT_EXPIRY_WORKER_ENABLED"] = "false"
    reset_settings_cache()
    settings = Settings.from_environment()
    yield settings
    dispose_engine()
    reset_settings_cache()


@pytest.fixture(scope="session")
def migrated_database(test_settings: Settings) -> Iterator[None]:
    try:
        with get_engine(test_settings).connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip(
            "Real PostgreSQL is required; start docker-compose.test.yml and set "
            "SEAT_TEST_DATABASE_URL when using another endpoint"
        )

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", test_settings.database_url)
    command.upgrade(config, "head")
    yield


@pytest.fixture()
def clean_database(migrated_database: None, test_settings: Settings) -> Iterator[None]:
    with get_engine(test_settings).begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE "
                "seat.seat_audit, seat.idempotency_records, "
                "seat.reservation_items, seat.seats, seat.reservations, "
                "seat.inventory_versions RESTART IDENTITY CASCADE"
            )
        )
    yield


def context(
    suffix: str,
    *,
    idempotency_key: str | None = None,
) -> RequestContext:
    return RequestContext(
        correlation_id=f"COR-{suffix}",
        idempotency_key=idempotency_key,
        caller_service="pytest",
        actor_id="TEST-ACTOR",
        schema_version="1.0",
    )


def create_inventory(
    settings: Settings,
    *,
    event_id: str = "EVT-TEST",
    seat_count: int = 10,
    blocked: set[int] | None = None,
) -> None:
    blocked = blocked or set()
    definitions = tuple(
        SeatDefinition(
            seat_id=f"A-{index:03d}",
            section="A",
            row_label="A",
            seat_number=f"{index:03d}",
            ticket_type="STANDARD",
            status=SeatStatus.BLOCKED if index in blocked else SeatStatus.AVAILABLE,
        )
        for index in range(1, seat_count + 1)
    )
    with session_scope(settings) as session:
        configure_inventory(
            session,
            settings,
            context(f"CONFIG-{event_id}"),
            event_id=event_id,
            inventory_version=1,
            seats=definitions,
        )
