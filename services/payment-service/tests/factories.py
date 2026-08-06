"""Shared test fixtures data.

One builder keeps every test suite on the same Settings shape, so adding a
configuration field does not mean editing four constructors.
"""

from typing import Any

from app.config import Settings

TEST_SERVICE_TOKEN = "test-service-token"  # noqa: S105 - test fixture, not a secret


def build_settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "app_name": "payment-service",
        "app_env": "test",
        "database_url": "postgresql+psycopg://payment:payment@localhost:5438/payment",
        "service_token": TEST_SERVICE_TOKEN,
        "db_pool_size": 1,
        "db_max_overflow": 0,
        "db_pool_timeout_seconds": 1,
        "db_connect_timeout_seconds": 1,
        "db_lock_timeout_ms": 1_000,
        "db_statement_timeout_ms": 5_000,
        "idempotency_ttl_seconds": 3_600,
        "log_level": "WARNING",
        "docs_enabled": True,
        "outbox_batch_size": 20,
        "outbox_max_attempts": 8,
        "outbox_poll_seconds": 5,
        "outbox_webhook_url": "",
        "outbox_webhook_secret": "",
        "outbox_webhook_timeout_seconds": 5,
        "provider_callback_secret": "test-provider-callback-secret",
        "provider_callback_replay_window_seconds": 300,
        "provider_callback_max_body_bytes": 65_536,
        "require_booking_evidence": False,
        "provider_reconciliation_max_attempts": 10,
        "provider_reconciliation_initial_delay_seconds": 5,
        "provider_reconciliation_max_delay_seconds": 300,
        "provider_reconciliation_batch_size": 20,
        "provider_reconciliation_poll_seconds": 5,
    }
    return Settings(**{**defaults, **overrides})
