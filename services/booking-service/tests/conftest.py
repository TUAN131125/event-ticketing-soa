from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from libs.platform_security import (
    ServiceJwtSigningSettings,
    ServiceJwtValidationSettings,
)

from app.config import Settings


@pytest.fixture(scope="session")
def booking_settings() -> Settings:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    issuer = "test-internal"
    return Settings(
        app_name="booking-service",
        app_env="test",
        database_url="postgresql+psycopg://booking:booking@localhost:5437/booking",
        service_jwt=ServiceJwtValidationSettings(
            None,
            base64.b64encode(public_pem).decode(),
            issuer,
            "booking-service",
            frozenset({"booking-orchestrator"}),
        ),
        service_jwt_signing=ServiceJwtSigningSettings(
            None,
            base64.b64encode(private_pem).decode(),
            issuer,
            "booking-service",
            "test-key",
            60,
        ),
        customer_service_url="http://customer.test",
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
