from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from libs.platform_security import ServiceJwtValidationSettings

from app.config import Settings


@pytest.fixture(scope="session")
def payment_settings() -> Settings:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    issuer = "test-internal"
    return Settings(
        app_name="payment-service",
        app_env="test",
        database_url="postgresql+psycopg://payment:payment@localhost:5438/payment",
        service_jwt=ServiceJwtValidationSettings(
            None,
            base64.b64encode(public_pem).decode(),
            issuer,
            "payment-service",
            frozenset({"booking-orchestrator"}),
        ),
        provider_hmac_secret="test-provider-hmac-secret",
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
