from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import Settings
from app.security.booking_access import HttpBookingAccessChecker
from app.security.token_validation import AuthenticatedPrincipal, JwksTokenValidator


def b64uint(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(value.to_bytes(length, "big")).rstrip(b"=").decode()


@pytest.mark.asyncio
async def test_jwt_signature_claims_algorithm_and_kid_validation(settings: Settings) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private_key.public_key().public_numbers()
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": "key-1",
                "n": b64uint(numbers.n),
                "e": b64uint(numbers.e),
            }
        ]
    }
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=jwks)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    validator = JwksTokenValidator(settings, client=client)
    now = datetime.now(UTC)
    claims = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": "U1",
        "iat": now,
        "nbf": now - timedelta(seconds=1),
        "exp": now + timedelta(minutes=5),
        "jti": "jti-1",
        "roles": ["CUSTOMER"],
        "customerId": "C001",
    }
    token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "key-1"})
    principal = await validator.validate(token)
    assert principal.customer_id == "C001"
    assert calls == 1
    bad_audience = jwt.encode(
        {**claims, "aud": "wrong"}, private_key, algorithm="RS256", headers={"kid": "key-1"}
    )
    with pytest.raises(Exception, match="Authentication is required"):
        await validator.validate(bad_audience)
    unknown = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "unknown"})
    with pytest.raises(Exception, match="Authentication is required"):
        await validator.validate(unknown)
    assert calls == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_booking_access_checker_owner_admin_and_dependency_fail_closed(
    settings: Settings,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-service-token"] == settings.booking_service_token
        if request.url.path.endswith("BK-error"):
            raise httpx.ConnectError("down")
        return httpx.Response(200, json={"bookingId": "BK-1", "customerId": "C001"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    checker = HttpBookingAccessChecker(settings, client=client)
    owner = AuthenticatedPrincipal("U1", frozenset({"CUSTOMER"}), "one", "C001")
    stranger = AuthenticatedPrincipal("U2", frozenset({"CUSTOMER"}), "two", "C999")
    admin = AuthenticatedPrincipal("ADMIN1", frozenset({"ADMIN"}), "three")
    assert await checker.can_subscribe(owner, "BK-1", "corr") is True
    assert await checker.can_subscribe(stranger, "BK-1", "corr") is False
    assert await checker.can_subscribe(admin, "BK-1", "corr") is True
    assert await checker.can_subscribe(owner, "BK-error", "corr") is False
    await client.aclose()


def test_production_configuration_rejects_insecure_values() -> None:
    with pytest.raises(ValueError, match="Wildcard"):
        Settings(app_env="production", allowed_ws_origins=("*",))
    with pytest.raises(ValueError, match="HTTPS"):
        Settings(app_env="production", allowed_ws_origins=("https://app.example",))
    with pytest.raises(ValueError, match="authentication modes"):
        Settings(
            app_env="production",
            allowed_ws_origins=("https://app.example",),
            jwt_issuer="https://identity.example",
            jwks_url="https://identity.example/.well-known/jwks.json",
            internal_service_token="a" * 32,
            booking_service_token="b" * 32,
            allow_query_token=True,
        )
    with pytest.raises(ValueError, match="ticket public key"):
        Settings(
            app_env="production",
            allowed_ws_origins=("https://app.example",),
            jwt_issuer="https://identity.example",
            jwks_url="https://identity.example/.well-known/jwks.json",
            internal_service_token="a" * 32,
            booking_service_token="b" * 32,
        )


def test_event_schema_rejects_naive_time_unknown_fields_and_sensitive_shape() -> None:
    from pydantic import ValidationError

    from app.schemas.messages import RealtimeStatusEvent

    base = {
        "messageId": "m1",
        "bookingId": "BK-1",
        "status": "PENDING",
        "sequence": 1,
        "occurredAt": "2026-08-03T03:00:00Z",
        "correlationId": "corr",
        "message": "safe",
    }
    with pytest.raises(ValidationError):
        RealtimeStatusEvent.model_validate({**base, "cardNumber": "4111111111111111"})
    with pytest.raises(ValidationError):
        RealtimeStatusEvent.model_validate({**base, "occurredAt": "2026-08-03T03:00:00"})
    with pytest.raises(ValidationError):
        RealtimeStatusEvent.model_validate({**base, "message": "card number 4111 1111 1111 1111"})


def test_generated_openapi_describes_internal_event_body(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    body_schema = schema["paths"]["/internal/status-events"]["post"]["requestBody"]
    properties = body_schema["content"]["application/json"]["schema"]["properties"]
    assert {
        "messageId",
        "bookingId",
        "status",
        "sequence",
        "occurredAt",
        "correlationId",
        "message",
    } <= properties.keys()
