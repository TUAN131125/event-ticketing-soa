"""Environment-backed application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _integer(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings with safe defaults for local development."""

    app_name: str
    app_env: str
    database_url: str
    service_token: str
    soap_public_url: str
    max_xml_bytes: int
    min_hold_seconds: int
    max_hold_seconds: int
    default_hold_seconds: int
    max_extension_seconds: int
    max_extend_count: int
    expiry_batch_size: int
    expiry_poll_seconds: int
    db_lock_timeout_ms: int
    db_statement_timeout_ms: int
    idempotency_ttl_seconds: int
    db_pool_size: int
    db_max_overflow: int
    sql_echo: bool
    expiry_worker_enabled: bool
    log_level: str

    @classmethod
    def from_environment(cls) -> Settings:
        min_hold = _integer("SEAT_MIN_HOLD_SECONDS", 30, minimum=1, maximum=3600)
        max_hold = _integer(
            "SEAT_MAX_HOLD_SECONDS", 900, minimum=min_hold, maximum=7200
        )
        default_hold = _integer(
            "SEAT_DEFAULT_HOLD_SECONDS",
            600,
            minimum=min_hold,
            maximum=max_hold,
        )
        database_url = os.getenv(
            "SEAT_DATABASE_URL",
            "postgresql+psycopg://seat_inventory:seat_inventory@localhost:5433/seat_inventory",
        )
        if database_url.startswith("postgres://"):
            database_url = database_url.replace(
                "postgres://", "postgresql+psycopg://", 1
            )
        elif database_url.startswith("postgresql://"):
            database_url = database_url.replace(
                "postgresql://", "postgresql+psycopg://", 1
            )

        return cls(
            app_name="seat-inventory-service",
            app_env=os.getenv("SEAT_APP_ENV", "local"),
            database_url=database_url,
            service_token=os.getenv("SEAT_SERVICE_TOKEN", "local-development-token"),
            soap_public_url=os.getenv(
                "SEAT_SOAP_PUBLIC_URL", "http://localhost:8003/soap"
            ),
            max_xml_bytes=_integer(
                "SEAT_MAX_XML_BYTES", 262_144, minimum=1024, maximum=2_097_152
            ),
            min_hold_seconds=min_hold,
            max_hold_seconds=max_hold,
            default_hold_seconds=default_hold,
            max_extension_seconds=_integer(
                "SEAT_MAX_EXTENSION_SECONDS", 300, minimum=1, maximum=3600
            ),
            max_extend_count=_integer(
                "SEAT_MAX_EXTEND_COUNT", 1, minimum=0, maximum=10
            ),
            expiry_batch_size=_integer(
                "SEAT_EXPIRY_BATCH_SIZE", 100, minimum=1, maximum=1000
            ),
            expiry_poll_seconds=_integer(
                "SEAT_EXPIRY_POLL_SECONDS", 3, minimum=1, maximum=300
            ),
            db_lock_timeout_ms=_integer(
                "SEAT_DB_LOCK_TIMEOUT_MS", 1500, minimum=50, maximum=30_000
            ),
            db_statement_timeout_ms=_integer(
                "SEAT_DB_STATEMENT_TIMEOUT_MS", 5000, minimum=100, maximum=60_000
            ),
            idempotency_ttl_seconds=_integer(
                "SEAT_IDEMPOTENCY_TTL_SECONDS",
                86_400,
                minimum=300,
                maximum=604_800,
            ),
            db_pool_size=_integer("SEAT_DB_POOL_SIZE", 20, minimum=1, maximum=100),
            db_max_overflow=_integer(
                "SEAT_DB_MAX_OVERFLOW", 20, minimum=0, maximum=100
            ),
            sql_echo=_boolean("SEAT_SQL_ECHO", False),
            expiry_worker_enabled=_boolean("SEAT_EXPIRY_WORKER_ENABLED", True),
            log_level=os.getenv("SEAT_LOG_LEVEL", "INFO").upper(),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_environment()


def reset_settings_cache() -> None:
    """Allow tests to replace environment-backed configuration."""

    get_settings.cache_clear()
