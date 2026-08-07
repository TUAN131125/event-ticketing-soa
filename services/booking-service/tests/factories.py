"""Shared Settings builder for the Booking test suites.

One builder keeps every suite on the same Settings shape, so adding a configuration field
does not mean editing three constructors.
"""

from typing import Any

from app.config import Settings
from tests.service_jwt import validation_settings


def build_settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "app_name": "booking-service",
        "app_env": "test",
        "database_url": "postgresql+psycopg://booking:booking@localhost:5437/booking",
        "service_token": "test-service-token",
        "db_pool_size": 1,
        "db_max_overflow": 0,
        "db_pool_timeout_seconds": 1,
        "db_connect_timeout_seconds": 1,
        "db_lock_timeout_ms": 1_000,
        "db_statement_timeout_ms": 5_000,
        "idempotency_ttl_seconds": 3_600,
        "log_level": "WARNING",
        "docs_enabled": True,
        "service_jwt": validation_settings(),
    }
    return Settings(**{**defaults, **overrides})
