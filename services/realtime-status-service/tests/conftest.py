from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import Unauthenticated
from app.main import create_app
from app.security.token_validation import AuthenticatedPrincipal


class FakeTokenValidator:
    async def validate(self, token: str) -> AuthenticatedPrincipal:
        if token == "owner-token":
            return AuthenticatedPrincipal("C001", frozenset({"CUSTOMER"}), "jti-owner")
        if token == "other-token":
            return AuthenticatedPrincipal("C999", frozenset({"CUSTOMER"}), "jti-other")
        if token == "admin-token":
            return AuthenticatedPrincipal("U-ADMIN", frozenset({"ADMIN"}), "jti-admin")
        raise Unauthenticated()


class FakeAccessChecker:
    async def can_subscribe(
        self, principal: AuthenticatedPrincipal, booking_id: str, correlation_id: str
    ) -> bool:
        del correlation_id
        return "ADMIN" in principal.roles or (
            principal.subject == "C001" and booking_id in {"BK-1", "BK-2"}
        )


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        host="127.0.0.1",
        allowed_ws_origins=("http://localhost:3000",),
        jwt_issuer="http://identity.test",
        jwt_audience="public-esb",
        jwks_url="http://identity.test/jwks",
        internal_service_token="test-internal-token",
        booking_authorization_url="http://booking.test/bookings/{bookingId}",
        booking_service_token="test-booking-token",
        heartbeat_interval_seconds=0.05,
        idle_timeout_seconds=0.2,
        cleanup_interval_seconds=0.05,
        send_timeout_seconds=0.1,
        max_event_bytes=1024,
    )


@pytest.fixture
def client(settings: Settings) -> AsyncIterator[TestClient]:
    app = create_app(
        settings, token_validator=FakeTokenValidator(), access_checker=FakeAccessChecker()
    )
    with TestClient(app) as test_client:
        yield test_client


def ws_headers(origin: str = "http://localhost:3000") -> dict[str, str]:
    return {"Origin": origin, "X-Correlation-ID": "corr-ws"}


def internal_headers(
    token: str = "test-internal-token", caller: str = "booking-service"
) -> dict[str, str]:
    return {
        "X-Service-Token": token,
        "X-Caller-Service": caller,
        "X-Correlation-ID": "corr-http",
        "Content-Type": "application/json",
    }


def event(
    message_id: str = "msg-1", booking_id: str = "BK-1", sequence: int = 1
) -> dict[str, object]:
    return {
        "messageId": message_id,
        "bookingId": booking_id,
        "status": "PENDING",
        "sequence": sequence,
        "occurredAt": "2026-08-03T03:00:00Z",
        "correlationId": "corr-event",
        "message": "Booking is being processed",
    }
