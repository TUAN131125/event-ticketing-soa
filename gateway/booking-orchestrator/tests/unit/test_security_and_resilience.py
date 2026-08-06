import time

import jwt
import pytest

from app.domain.errors import Conflict, EsbError
from app.domain.models import Principal, RequestContext
from app.persistence.repositories import InMemoryRepository
from app.resilience.policies import ResiliencePolicy
from app.security.auth import JwtVerifier
from app.security.ws_ticket import WebSocketTicketIssuer


@pytest.mark.asyncio
async def test_jwt_signature_is_verified():
    now = int(time.time())
    verifier = JwtVerifier(audience="api", shared_secret="correct-secret-at-least-thirty-two-bytes")
    valid = jwt.encode({"sub": "u1", "aud": "api", "exp": now + 60, "roles": ["ADMIN"]}, "correct-secret-at-least-thirty-two-bytes", algorithm="HS256")
    principal = await verifier.verify("Bearer " + valid)
    assert principal.subject == "u1" and "ADMIN" in principal.roles
    invalid = jwt.encode({"sub": "u1", "aud": "api", "exp": now + 60}, "wrong-secret-at-least-thirty-two-bytesxx", algorithm="HS256")
    with pytest.raises(EsbError) as exc:
        await verifier.verify("Bearer " + invalid)
    assert exc.value.code == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_ws_ticket_idempotency_and_booking_binding():
    repository = InMemoryRepository()
    issuer = WebSocketTicketIssuer("x" * 32, repository, ttl_seconds=30)
    first = await issuer.issue("b1", "u1", "idem-ws-ticket")
    second = await issuer.issue("b1", "u1", "idem-ws-ticket")
    assert first == second
    claims = jwt.decode(first["ticket"], "x" * 32, algorithms=["HS256"], audience="realtime-status-service")
    assert claims["bookingId"] == "b1" and claims["scope"] == "booking:status:read"
    with pytest.raises(Conflict):
        await issuer.issue("b2", "u1", "idem-ws-ticket")


@pytest.mark.asyncio
async def test_safe_read_is_retried_but_side_effect_is_not():
    policy = ResiliencePolicy(safe_attempts=3, command_attempts=2)
    calls = 0
    async def flaky():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise OSError("temporary")
        return "ok"
    assert await policy.execute("event", flaky, mode="safe_read", deadline=time.monotonic() + 3) == "ok"
    assert calls == 3
    calls = 0
    async def failing():
        nonlocal calls
        calls += 1
        raise OSError("down")
    with pytest.raises(EsbError):
        await policy.execute("payment", failing, mode="side_effect", deadline=time.monotonic() + 3)
    assert calls == 1
