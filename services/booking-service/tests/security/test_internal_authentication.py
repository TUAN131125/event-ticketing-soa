"""Internal Booking operations are gated by the shared Service JWT.

X-Service-Token used to be the mechanism. These tests now prove it carries no authority at
all, and that the caller identity comes from the signed `sub` claim rather than from any
header the caller can set.
"""

from __future__ import annotations

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.factories import build_settings
from tests.service_jwt import (
    AUDIENCE,
    CALLER,
    ISSUER,
    KEY_ID,
    auth_header,
    issue_token,
    private_key_base64,
)

BOOKING_PATH = "/bookings/BK00000001"


def client() -> TestClient:
    return TestClient(create_app(build_settings()))


def raw_token(**claim_overrides) -> str:
    """Hand-rolled only where a *malformed* token is the thing under test."""
    import base64

    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "sub": CALLER,
        "aud": AUDIENCE,
        "roles": ["SERVICE"],
        "iat": now,
        "exp": now + 60,
        "jti": f"test-{now}-{claim_overrides.get('jti_suffix', '0')}",
    }
    claims.pop("jti_suffix", None)
    claim_overrides.pop("jti_suffix", None)
    for key, value in claim_overrides.items():
        if value is None:
            claims.pop(key, None)
        else:
            claims[key] = value
    private_key = base64.b64decode(private_key_base64()).decode()
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": KEY_ID})


def test_missing_authorization_is_rejected() -> None:
    with client() as api:
        response = api.get(BOOKING_PATH)
    assert response.status_code == 401
    assert "X-Correlation-ID" in response.headers


def test_malformed_bearer_token_is_rejected() -> None:
    with client() as api:
        response = api.get(BOOKING_PATH, headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


def test_token_signed_by_another_key_is_rejected() -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    foreign = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = foreign.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": ISSUER,
            "sub": CALLER,
            "aud": AUDIENCE,
            "roles": ["SERVICE"],
            "iat": now,
            "exp": now + 60,
            "jti": "foreign-key",
        },
        pem,
        algorithm="RS256",
        headers={"kid": KEY_ID},
    )
    with client() as api:
        response = api.get(BOOKING_PATH, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_wrong_issuer_is_rejected() -> None:
    with client() as api:
        response = api.get(
            BOOKING_PATH, headers=auth_header(issuer="https://evil.example")
        )
    assert response.status_code == 401


def test_wrong_audience_is_rejected() -> None:
    """A token minted for another service must not open this one."""
    with client() as api:
        response = api.get(BOOKING_PATH, headers=auth_header("payment-service"))
    assert response.status_code == 401


def test_expired_token_is_rejected() -> None:
    now = int(time.time())
    token = raw_token(iat=now - 600, exp=now - 300)
    with client() as api:
        response = api.get(BOOKING_PATH, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


@pytest.mark.parametrize("claim", ["sub", "aud", "roles", "exp", "jti", "iss"])
def test_missing_required_claim_is_rejected(claim: str) -> None:
    token = raw_token(**{claim: None, "jti_suffix": claim})
    with client() as api:
        response = api.get(BOOKING_PATH, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_non_service_role_is_rejected() -> None:
    token = raw_token(roles=["CUSTOMER"], jti_suffix="role")
    with client() as api:
        response = api.get(BOOKING_PATH, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_disallowed_caller_subject_is_rejected() -> None:
    """The shared verifier treats an unlisted subject as an authentication failure."""
    with client() as api:
        response = api.get(BOOKING_PATH, headers=auth_header(subject="ticket-service"))
    assert response.status_code == 401


def test_service_token_header_cannot_bypass_jwt() -> None:
    """The retired mechanism must carry no authority whatsoever."""
    with client() as api:
        response = api.get(
            BOOKING_PATH,
            headers={
                "X-Service-Token": "test-service-token",
                "X-Caller-Service": "booking-orchestrator",
            },
        )
    assert response.status_code == 401


def test_forged_caller_header_does_not_override_the_jwt_subject() -> None:
    """A valid token plus a lying header must not change who the caller is."""
    headers = auth_header()
    headers["X-Caller-Service"] = "attacker-service"
    with client() as api:
        response = api.get(BOOKING_PATH, headers=headers)
    # Authentication succeeds on the token and the request reaches the data layer, so the
    # forged header changed nothing. These suites run without PostgreSQL, so the request
    # then surfaces as a dependency failure rather than as an auth failure.
    assert response.status_code not in {401, 403}
    assert response.status_code == 503


def test_valid_orchestrator_token_is_accepted() -> None:
    with client() as api:
        response = api.get(BOOKING_PATH, headers=auth_header())
    # Getting past authentication to the data layer is the assertion; these suites run
    # without PostgreSQL so the call ends in a dependency error, never a 401/403.
    assert response.status_code not in {401, 403}
    assert response.status_code == 503


def test_error_response_never_echoes_the_token() -> None:
    token = issue_token()
    with client() as api:
        response = api.get(BOOKING_PATH, headers={"Authorization": f"Bearer {token}x"})
    assert response.status_code == 401
    body = response.text
    assert token not in body
    assert "Bearer" not in body
    assert "X-Correlation-ID" in response.headers


def test_liveness_is_public_and_does_not_touch_database() -> None:
    with client() as api:
        response = api.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "UP"
