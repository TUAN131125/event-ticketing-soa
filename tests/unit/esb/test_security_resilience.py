from __future__ import annotations

import asyncio
import base64
import time
from datetime import datetime, timezone

import httpx
import jwt
import pytest
from app.config import Settings
from app.domain.errors import AuthenticationFailed, BusinessFault, DependencyFailure
from app.resilience.policies import (
    Bulkhead,
    CircuitBreaker,
    ResilienceExecutor,
    RetryClass,
)
from app.security.jwt import JwksVerifier, WebSocketTicketIssuer
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fakes import request_context


def key_material(kid: str = "identity-1") -> tuple[str, dict[str, str]]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    numbers = key.public_key().public_numbers()
    encode = lambda value: (
        base64.urlsafe_b64encode(value.to_bytes((value.bit_length() + 7) // 8, "big"))
        .rstrip(b"=")
        .decode()
    )
    return private, {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": encode(numbers.n),
        "e": encode(numbers.e),
    }


@pytest.mark.asyncio
async def test_jwks_signature_claim_validation_cache_and_unknown_kid_refresh() -> None:
    private, jwk = key_material()
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"keys": [jwk]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    verifier = JwksVerifier(
        "https://identity.test/jwks", "identity-service", "public-esb", 300, client
    )
    now = int(datetime.now(timezone.utc).timestamp())
    claims = {
        "sub": "identity-subject",
        "roles": ["CUSTOMER"],
        "iss": "identity-service",
        "aud": "public-esb",
        "iat": now,
        "exp": now + 60,
    }
    token = jwt.encode(
        claims, private, algorithm="RS256", headers={"kid": "identity-1"}
    )
    assert (await verifier.verify(token)).subject == "identity-subject"
    assert (await verifier.verify(token)).roles == ("CUSTOMER",)
    assert calls == 1

    unknown = jwt.encode(
        claims, private, algorithm="RS256", headers={"kid": "rotated-key"}
    )
    with pytest.raises(AuthenticationFailed):
        await verifier.verify(unknown)
    assert calls == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_jwks_rejects_wrong_audience_and_algorithm() -> None:
    private, jwk = key_material()
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"keys": [jwk]})
        )
    )
    verifier = JwksVerifier(
        "https://identity.test/jwks", "identity-service", "public-esb", 300, client
    )
    now = int(time.time())
    wrong_audience = jwt.encode(
        {
            "sub": "s",
            "roles": [],
            "iss": "identity-service",
            "aud": "wrong",
            "iat": now,
            "exp": now + 60,
        },
        private,
        algorithm="RS256",
        headers={"kid": "identity-1"},
    )
    with pytest.raises(AuthenticationFailed):
        await verifier.verify(wrong_audience)
    with pytest.raises(AuthenticationFailed):
        await verifier.verify(
            jwt.encode(
                {"sub": "s"},
                "shared-secret-that-is-at-least-32-bytes",
                algorithm="HS256",
                headers={"kid": "identity-1"},
            )
        )
    await client.aclose()


def test_websocket_ticket_is_signed_booking_bound_short_lived_and_single_use_ready() -> (
    None
):
    private, _ = key_material("ws-1")
    issuer = WebSocketTicketIssuer(
        private, "booking-orchestrator", "realtime-status-service", "ws-1", 60
    )
    token, expires = issuer.issue("identity-subject", "BK-1")
    public = serialization.load_pem_private_key(
        private.encode(), password=None
    ).public_key()
    claims = jwt.decode(
        token,
        public,
        algorithms=["RS256"],
        audience="realtime-status-service",
        issuer="booking-orchestrator",
    )
    assert claims["sub"] == "identity-subject"
    assert claims["bookingId"] == "BK-1"
    assert claims["scope"] == "booking:status:read"
    assert claims["jti"]
    assert 0 < claims["exp"] - claims["iat"] <= 60
    assert int(expires.timestamp()) == claims["exp"]


def test_production_config_rejects_insecure_defaults() -> None:
    with pytest.raises(ValueError):
        Settings(environment="production")
    with pytest.raises(ValueError):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://db/prod",
            internal_service_private_key="key",
            ws_ticket_private_key="key",
            docs_enabled=False,
            notification_webhook_secret="short",
        )
    production = {
        "environment": "production",
        "database_url": "postgresql+asyncpg://db/prod",
        "internal_service_private_key": "key",
        "ws_ticket_private_key": "key",
        "docs_enabled": False,
        "create_schema_on_start": False,
        "notification_webhook_secret": "n" * 32,
        "seat_service_token": "s" * 32,
        "realtime_internal_service_token": "r" * 32,
    }
    with pytest.raises(ValueError, match="Seat service token"):
        Settings(**{**production, "seat_service_token": "short"})
    with pytest.raises(ValueError, match="Realtime internal service token"):
        Settings(**{**production, "realtime_internal_service_token": "short"})


@pytest.mark.asyncio
async def test_safe_read_retry_and_business_fault_is_not_retried() -> None:
    executor = ResilienceExecutor(
        {RetryClass.SAFE_READ: 2, RetryClass.NONE: 1},
        0,
        CircuitBreaker(5, 1),
        Bulkhead(2),
    )
    attempts = 0

    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("offline")
        return "ok"

    assert (
        await executor.execute(flaky, RetryClass.SAFE_READ, request_context()) == "ok"
    )
    assert attempts == 2

    business_attempts = 0

    async def invalid() -> str:
        nonlocal business_attempts
        business_attempts += 1
        raise BusinessFault("INVALID", "Invalid.", 409, False)

    with pytest.raises(BusinessFault):
        await executor.execute(invalid, RetryClass.SAFE_READ, request_context())
    assert business_attempts == 1


@pytest.mark.asyncio
async def test_circuit_breaker_and_bulkhead_reject_excess_work() -> None:
    circuit = CircuitBreaker(1, 60)
    circuit.failure()
    with pytest.raises(DependencyFailure) as opened:
        circuit.before_call()
    assert opened.value.code == "CIRCUIT_OPEN"

    bulkhead = Bulkhead(1)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def slow() -> str:
        entered.set()
        await release.wait()
        return "done"

    first = asyncio.create_task(bulkhead.run(slow))
    await entered.wait()
    with pytest.raises(DependencyFailure) as full:
        await bulkhead.run(slow)
    assert full.value.code == "BULKHEAD_FULL"
    release.set()
    assert await first == "done"
