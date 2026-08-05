"""Environment-backed Payment Service configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from libs.platform_security import ServiceJwtValidationSettings


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
    value = os.getenv("PAYMENT_DATABASE_URL", "").strip()
    if not value:
        raise ValueError("PAYMENT_DATABASE_URL is required")
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
    service_jwt: ServiceJwtValidationSettings
    provider_hmac_secret: str
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
        app_env = os.getenv("PAYMENT_APP_ENV", "local").strip().lower()
        provider_hmac_secret = os.getenv("PAYMENT_PROVIDER_HMAC_SECRET", "").strip()
        if not provider_hmac_secret:
            raise ValueError("PAYMENT_PROVIDER_HMAC_SECRET is required")
        return cls(
            app_name="payment-service",
            app_env=app_env,
            database_url=_database_url(),
            service_jwt=ServiceJwtValidationSettings.from_environment(
                "PAYMENT", audience="payment-service"
            ),
            provider_hmac_secret=provider_hmac_secret,
            db_pool_size=_integer("PAYMENT_DB_POOL_SIZE", 10, 1, 100),
            db_max_overflow=_integer("PAYMENT_DB_MAX_OVERFLOW", 20, 0, 100),
            db_pool_timeout_seconds=_integer(
                "PAYMENT_DB_POOL_TIMEOUT_SECONDS", 5, 1, 60
            ),
            db_connect_timeout_seconds=_integer(
                "PAYMENT_DB_CONNECT_TIMEOUT_SECONDS", 3, 1, 30
            ),
            db_lock_timeout_ms=_integer(
                "PAYMENT_DB_LOCK_TIMEOUT_MS", 2_000, 100, 60_000
            ),
            db_statement_timeout_ms=_integer(
                "PAYMENT_DB_STATEMENT_TIMEOUT_MS", 10_000, 500, 120_000
            ),
            idempotency_ttl_seconds=_integer(
                "PAYMENT_IDEMPOTENCY_TTL_SECONDS", 86_400, 300, 2_592_000
            ),
            log_level=os.getenv("PAYMENT_LOG_LEVEL", "INFO").upper(),
            docs_enabled=_boolean(
                "PAYMENT_DOCS_ENABLED", default=app_env != "production"
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_environment()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
