"""Environment-backed Ticket Service configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
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


def _database_url() -> str:
    value = os.getenv("TICKET_DATABASE_URL", "").strip()
    if not value:
        raise ValueError("TICKET_DATABASE_URL is required")
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    app_env: str
    database_url: str
    service_token: str
    qr_signing_key: str
    db_pool_size: int
    db_max_overflow: int
    db_pool_timeout_seconds: int
    db_connect_timeout_seconds: int
    db_lock_timeout_ms: int
    db_statement_timeout_ms: int
    idempotency_ttl_seconds: int
    log_level: str
    docs_enabled: bool

    @classmethod
    def from_environment(cls) -> Settings:
        app_env = os.getenv("TICKET_APP_ENV", "local").strip().lower()
        service_token = os.getenv("TICKET_SERVICE_TOKEN", "").strip()
        qr_signing_key = os.getenv("TICKET_QR_SIGNING_KEY", "").strip()
        if not service_token:
            raise ValueError("TICKET_SERVICE_TOKEN is required")
        if not qr_signing_key:
            raise ValueError("TICKET_QR_SIGNING_KEY is required")
        if app_env == "production":
            if len(service_token) < 32:
                raise ValueError(
                    "TICKET_SERVICE_TOKEN must be a non-default value of at least "
                    "32 characters in production"
                )
            if len(qr_signing_key) < 32:
                raise ValueError(
                    "TICKET_QR_SIGNING_KEY must be a non-default value of at least "
                    "32 characters in production"
                )
        return cls(
            app_name="ticket-service",
            app_env=app_env,
            database_url=_database_url(),
            service_token=service_token,
            qr_signing_key=qr_signing_key,
            db_pool_size=_integer("TICKET_DB_POOL_SIZE", 10, 1, 100),
            db_max_overflow=_integer("TICKET_DB_MAX_OVERFLOW", 20, 0, 100),
            db_pool_timeout_seconds=_integer(
                "TICKET_DB_POOL_TIMEOUT_SECONDS", 5, 1, 60
            ),
            db_connect_timeout_seconds=_integer(
                "TICKET_DB_CONNECT_TIMEOUT_SECONDS", 3, 1, 30
            ),
            db_lock_timeout_ms=_integer(
                "TICKET_DB_LOCK_TIMEOUT_MS", 2_000, 100, 60_000
            ),
            db_statement_timeout_ms=_integer(
                "TICKET_DB_STATEMENT_TIMEOUT_MS", 10_000, 500, 120_000
            ),
            idempotency_ttl_seconds=_integer(
                "TICKET_IDEMPOTENCY_TTL_SECONDS", 86_400, 300, 2_592_000
            ),
            log_level=os.getenv("TICKET_LOG_LEVEL", "INFO").upper(),
            docs_enabled=_boolean(
                "TICKET_DOCS_ENABLED", default=app_env != "production"
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_environment()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
