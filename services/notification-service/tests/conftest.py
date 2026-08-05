from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from libs.platform_security import ServiceJwtValidationSettings

from app.config import Settings


@pytest.fixture
def notification_settings() -> Settings:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return Settings(
        app_env="test",
        log_level="WARNING",
        service_name="notification-service",
        database_url="postgresql+psycopg://notification:test@localhost/notification",
        db_pool_size=1,
        db_max_overflow=0,
        sql_echo=False,
        service_jwt=ServiceJwtValidationSettings(
            None,
            base64.b64encode(public).decode(),
            "test-internal",
            "notification-service",
            frozenset({"booking-orchestrator"}),
        ),
        webhook_hmac_secret="test-webhook-secret",
        webhook_tolerance_seconds=300,
    )
