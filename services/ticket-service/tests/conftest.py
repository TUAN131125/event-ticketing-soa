from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from libs.platform_security import ServiceJwtValidationSettings

from app.config import Settings


@pytest.fixture(scope="session")
def ticket_settings() -> Settings:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return Settings(
        app_name="ticket-service",
        app_env="test",
        database_url="postgresql+psycopg://ticket:ticket@localhost:5439/ticket",
        service_jwt=ServiceJwtValidationSettings(
            None,
            base64.b64encode(public_pem).decode(),
            "test-internal",
            "ticket-service",
            frozenset({"booking-orchestrator"}),
        ),
        qr_signing_key="test-qr-signing-key-that-is-long-enough",
        db_pool_size=1,
        db_max_overflow=0,
        db_pool_timeout_seconds=1,
        db_connect_timeout_seconds=1,
        db_lock_timeout_ms=1_000,
        db_statement_timeout_ms=5_000,
        idempotency_ttl_seconds=3_600,
        log_level="WARNING",
        docs_enabled=True,
    )
