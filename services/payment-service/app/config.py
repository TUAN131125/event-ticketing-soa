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


LOCAL_ENV = "local"
DEVELOPMENT_TOKEN = "local-development-token"  # noqa: S105 - placeholder, not a secret
DEVELOPMENT_CALLBACK_SECRET = "local-provider-callback-secret"  # noqa: S105
MINIMUM_TOKEN_LENGTH = 32


def _service_token(app_env: str) -> str:
    """Resolve the internal service token, refusing weak values outside local.

    Only the local environment may fall back to the shared placeholder. Any other
    environment must supply its own value, so a staging deployment that forgets
    the variable fails to start instead of accepting a publicly known token.
    """
    configured = os.getenv("PAYMENT_SERVICE_TOKEN")
    if app_env == LOCAL_ENV:
        return configured or DEVELOPMENT_TOKEN
    if not configured:
        raise ValueError(
            "PAYMENT_SERVICE_TOKEN must be set when PAYMENT_APP_ENV is not 'local'"
        )
    if configured == DEVELOPMENT_TOKEN:
        raise ValueError(
            "PAYMENT_SERVICE_TOKEN must not reuse the shared development token"
        )
    if len(configured) < MINIMUM_TOKEN_LENGTH:
        raise ValueError(
            f"PAYMENT_SERVICE_TOKEN must be at least {MINIMUM_TOKEN_LENGTH} characters"
        )
    return configured


def _provider_callback_secret(app_env: str) -> str:
    configured = os.getenv("PAYMENT_PROVIDER_CALLBACK_SECRET")
    if app_env == LOCAL_ENV:
        return configured or DEVELOPMENT_CALLBACK_SECRET
    if not configured:
        raise ValueError(
            "PAYMENT_PROVIDER_CALLBACK_SECRET must be set when "
            "PAYMENT_APP_ENV is not 'local'"
        )
    if configured == DEVELOPMENT_CALLBACK_SECRET:
        raise ValueError(
            "PAYMENT_PROVIDER_CALLBACK_SECRET must not reuse the shared "
            "development secret"
        )
    if len(configured) < MINIMUM_TOKEN_LENGTH:
        raise ValueError(
            "PAYMENT_PROVIDER_CALLBACK_SECRET must be at least "
            f"{MINIMUM_TOKEN_LENGTH} characters"
        )
    return configured


def _database_url() -> str:
    value = os.getenv(
        "PAYMENT_DATABASE_URL",
        "postgresql+psycopg://payment:payment@localhost:5438/payment",
    )
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
    db_pool_size: int
    db_max_overflow: int
    db_pool_timeout_seconds: int
    db_connect_timeout_seconds: int
    db_lock_timeout_ms: int
    db_statement_timeout_ms: int
    idempotency_ttl_seconds: int
    log_level: str
    docs_enabled: bool
    outbox_batch_size: int
    outbox_max_attempts: int
    outbox_poll_seconds: int
    outbox_webhook_url: str
    outbox_webhook_secret: str
    outbox_webhook_timeout_seconds: int
    provider_callback_secret: str
    provider_callback_replay_window_seconds: int
    provider_callback_max_body_bytes: int
    require_booking_evidence: bool
    provider_reconciliation_max_attempts: int
    provider_reconciliation_initial_delay_seconds: int
    provider_reconciliation_max_delay_seconds: int
    provider_reconciliation_batch_size: int
    provider_reconciliation_poll_seconds: int
    # Optional so existing test factories keep working; from_environment always
    # supplies it and main.py requires it at startup.
    service_jwt: ServiceJwtValidationSettings | None = None

    @property
    def outbox_webhook_enabled(self) -> bool:
        return bool(self.outbox_webhook_url)

    @classmethod
    def from_environment(cls) -> Settings:
        app_env = os.getenv("PAYMENT_APP_ENV", "local").strip().lower()
        webhook_url = os.getenv("PAYMENT_OUTBOX_WEBHOOK_URL", "").strip()
        webhook_secret = os.getenv("PAYMENT_OUTBOX_WEBHOOK_SECRET", "")
        if webhook_url and not webhook_secret:
            raise ValueError(
                "PAYMENT_OUTBOX_WEBHOOK_SECRET is required when a webhook URL is set"
            )
        if webhook_url and not webhook_url.startswith(("http://", "https://")):
            raise ValueError("PAYMENT_OUTBOX_WEBHOOK_URL must be an http(s) URL")
        return cls(
            app_name="payment-service",
            app_env=app_env,
            database_url=_database_url(),
            service_token=_service_token(app_env),
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
            outbox_batch_size=_integer("PAYMENT_OUTBOX_BATCH_SIZE", 20, 1, 500),
            outbox_max_attempts=_integer("PAYMENT_OUTBOX_MAX_ATTEMPTS", 8, 1, 100),
            outbox_poll_seconds=_integer("PAYMENT_OUTBOX_POLL_SECONDS", 5, 1, 300),
            outbox_webhook_url=webhook_url,
            outbox_webhook_secret=webhook_secret,
            outbox_webhook_timeout_seconds=_integer(
                "PAYMENT_OUTBOX_WEBHOOK_TIMEOUT_SECONDS", 5, 1, 60
            ),
            provider_callback_secret=_provider_callback_secret(app_env),
            provider_callback_replay_window_seconds=_integer(
                "PAYMENT_PROVIDER_CALLBACK_REPLAY_WINDOW_SECONDS", 300, 30, 3600
            ),
            provider_callback_max_body_bytes=_integer(
                "PAYMENT_PROVIDER_CALLBACK_MAX_BODY_BYTES", 65536, 1024, 1048576
            ),
            require_booking_evidence=_boolean(
                "PAYMENT_REQUIRE_BOOKING_EVIDENCE", default=app_env != "local"
            ),
            provider_reconciliation_max_attempts=_integer(
                "PAYMENT_PROVIDER_RECONCILIATION_MAX_ATTEMPTS", 10, 1, 100
            ),
            provider_reconciliation_initial_delay_seconds=_integer(
                "PAYMENT_PROVIDER_RECONCILIATION_INITIAL_DELAY_SECONDS", 5, 1, 3600
            ),
            provider_reconciliation_max_delay_seconds=_integer(
                "PAYMENT_PROVIDER_RECONCILIATION_MAX_DELAY_SECONDS", 300, 1, 86400
            ),
            provider_reconciliation_batch_size=_integer(
                "PAYMENT_PROVIDER_RECONCILIATION_BATCH_SIZE", 20, 1, 500
            ),
            provider_reconciliation_poll_seconds=_integer(
                "PAYMENT_PROVIDER_RECONCILIATION_POLL_SECONDS", 5, 1, 300
            ),
            service_jwt=ServiceJwtValidationSettings.from_environment(
                "PAYMENT",
                audience="payment-service",
                default_allowed_subjects="booking-orchestrator",
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_environment()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
