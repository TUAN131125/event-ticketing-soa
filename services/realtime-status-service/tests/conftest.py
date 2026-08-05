from __future__ import annotations

import base64
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from libs.platform_security import (
    ServiceJwtSigner,
    ServiceJwtSigningSettings,
    ServiceJwtValidationSettings,
)

from app.config import Settings
from app.main import create_app
from app.security.ws_ticket import SignedWebSocketTicketValidator


@pytest.fixture(scope="session")
def security_material(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    directory = tmp_path_factory.mktemp("realtime-security")
    service_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    service_private_pem = service_private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    service_public_pem = service_private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    ticket_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ticket_public_path = Path(directory) / "ws-ticket-public.pem"
    ticket_public_path.write_bytes(
        ticket_private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return {
        "service_private": base64.b64encode(service_private_pem).decode(),
        "service_public": base64.b64encode(service_public_pem).decode(),
        "ticket_private": ticket_private,
        "ticket_public_path": ticket_public_path,
    }


@pytest.fixture
def settings(security_material: dict[str, Any]) -> Settings:
    return Settings(
        app_env="test",
        host="127.0.0.1",
        allowed_ws_origins=("http://localhost:3000",),
        service_jwt=ServiceJwtValidationSettings(
            None,
            security_material["service_public"],
            "test-internal",
            "realtime-status-service",
            frozenset({"booking-orchestrator", "booking-service"}),
        ),
        heartbeat_interval_seconds=0.05,
        idle_timeout_seconds=0.2,
        cleanup_interval_seconds=0.05,
        send_timeout_seconds=0.1,
        max_event_bytes=1024,
    )


@pytest.fixture
def service_signer(security_material: dict[str, Any]) -> ServiceJwtSigner:
    return ServiceJwtSigningSettings(
        None,
        security_material["service_private"],
        "test-internal",
        "booking-service",
        "test-key",
        60,
    ).signer()


@pytest.fixture
def internal_headers(service_signer: ServiceJwtSigner) -> Callable[[], dict[str, str]]:
    def headers() -> dict[str, str]:
        return {
            "Authorization": (f"Bearer {service_signer.issue('realtime-status-service')}"),
            "X-Correlation-ID": "corr-http-1234567890",
            "Content-Type": "application/json",
        }

    return headers


@pytest.fixture
def issue_ticket(security_material: dict[str, Any]) -> Callable[..., str]:
    def issue(**overrides: Any) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": "booking-orchestrator",
            "aud": "realtime-status-service",
            "sub": "identity-subject-1",
            "bookingId": "BK-1",
            "scope": "booking:status:read",
            "iat": now,
            "exp": now + 30,
            "jti": str(uuid4()),
        }
        claims.update(overrides)
        return jwt.encode(
            claims,
            security_material["ticket_private"],
            algorithm="RS256",
            headers={"kid": "esb-1"},
        )

    return issue


@pytest.fixture
def client(settings: Settings, security_material: dict[str, Any]) -> AsyncIterator[TestClient]:
    validator = SignedWebSocketTicketValidator(
        public_key_path=security_material["ticket_public_path"],
        issuer="booking-orchestrator",
        audience="realtime-status-service",
        key_id="esb-1",
        max_ttl_seconds=60,
    )
    with TestClient(create_app(settings, ws_ticket_validator=validator)) as test_client:
        yield test_client


def ws_headers(origin: str = "http://localhost:3000") -> dict[str, str]:
    return {"Origin": origin, "X-Correlation-ID": "corr-ws-1234567890"}


def event(
    message_id: str = "msg-1", booking_id: str = "BK-1", sequence: int = 1
) -> dict[str, object]:
    return {
        "messageId": message_id,
        "bookingId": booking_id,
        "status": "PENDING",
        "sequence": sequence,
        "occurredAt": "2026-08-03T03:00:00Z",
        "correlationId": "corr-event-1234567890",
        "message": "Booking is being processed",
    }
