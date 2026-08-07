"""Internal Payment operations are gated by the shared Service JWT.

The provider callback keeps its own HMAC scheme. The two must not substitute for one
another: a Service JWT cannot sign a webhook, and a webhook signature cannot drive an
internal payment command.
"""

from __future__ import annotations

import base64
import json
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.security.provider_callback import callback_signature
from tests.factories import TEST_SERVICE_TOKEN, build_settings
from tests.service_jwt import (
    AUDIENCE,
    CALLER,
    ISSUER,
    KEY_ID,
    auth_header,
    issue_token,
    private_key_base64,
)

PAYMENT_PATH = "/payments/PAY00000001"
CALLBACK_PATH = "/payments/provider-callback"


def client() -> TestClient:
    return TestClient(create_app(build_settings()))


def raw_token(**claim_overrides) -> str:
    """Hand-rolled only where a *malformed* token is the thing under test."""
    now = int(time.time())
    suffix = claim_overrides.pop("jti_suffix", "0")
    claims = {
        "iss": ISSUER,
        "sub": CALLER,
        "aud": AUDIENCE,
        "roles": ["SERVICE"],
        "iat": now,
        "exp": now + 60,
        "jti": f"test-{now}-{suffix}",
    }
    for key, value in claim_overrides.items():
        if value is None:
            claims.pop(key, None)
        else:
            claims[key] = value
    private_key = base64.b64decode(private_key_base64()).decode()
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": KEY_ID})


def test_missing_authorization_is_rejected() -> None:
    with client() as api:
        response = api.get(PAYMENT_PATH)
    assert response.status_code == 401
    assert "X-Correlation-ID" in response.headers


def test_malformed_bearer_token_is_rejected() -> None:
    with client() as api:
        response = api.get(PAYMENT_PATH, headers={"Authorization": "Bearer not-a-jwt"})
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
        response = api.get(PAYMENT_PATH, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_wrong_issuer_is_rejected() -> None:
    with client() as api:
        response = api.get(
            PAYMENT_PATH, headers=auth_header(issuer="https://evil.example")
        )
    assert response.status_code == 401


def test_wrong_audience_is_rejected() -> None:
    """A Booking-audience token must not open Payment."""
    with client() as api:
        response = api.get(PAYMENT_PATH, headers=auth_header("booking-service"))
    assert response.status_code == 401


def test_expired_token_is_rejected() -> None:
    now = int(time.time())
    token = raw_token(iat=now - 600, exp=now - 300)
    with client() as api:
        response = api.get(PAYMENT_PATH, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


@pytest.mark.parametrize("claim", ["sub", "aud", "roles", "exp", "jti", "iss"])
def test_missing_required_claim_is_rejected(claim: str) -> None:
    token = raw_token(**{claim: None, "jti_suffix": claim})
    with client() as api:
        response = api.get(PAYMENT_PATH, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_non_service_role_is_rejected() -> None:
    token = raw_token(roles=["CUSTOMER"], jti_suffix="role")
    with client() as api:
        response = api.get(PAYMENT_PATH, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_disallowed_caller_subject_is_rejected() -> None:
    with client() as api:
        response = api.get(PAYMENT_PATH, headers=auth_header(subject="ticket-service"))
    assert response.status_code == 401


def test_service_token_header_cannot_bypass_jwt() -> None:
    """The retired mechanism must carry no authority whatsoever."""
    with client() as api:
        response = api.get(
            PAYMENT_PATH,
            headers={
                "X-Service-Token": TEST_SERVICE_TOKEN,
                "X-Caller-Service": "booking-orchestrator",
            },
        )
    assert response.status_code == 401


def test_forged_caller_header_does_not_override_the_jwt_subject() -> None:
    headers = auth_header()
    headers["X-Caller-Service"] = "attacker-service"
    with client() as api:
        response = api.get(PAYMENT_PATH, headers=headers)
    # Past authentication and into the data layer, which is unavailable in this suite.
    assert response.status_code not in {401, 403}
    assert response.status_code == 503


def test_valid_orchestrator_token_is_accepted() -> None:
    with client() as api:
        response = api.get(PAYMENT_PATH, headers=auth_header())
    assert response.status_code not in {401, 403}
    assert response.status_code == 503


def test_error_response_never_echoes_the_token() -> None:
    token = issue_token()
    with client() as api:
        response = api.get(PAYMENT_PATH, headers={"Authorization": f"Bearer {token}x"})
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


# --- ServiceJwt and WebhookHmac must stay separate ------------------------------------


def callback_body() -> bytes:
    return json.dumps(
        {
            "eventId": "evt-auth-boundary",
            "paymentId": "PAY00000001",
            "operation": "AUTHORIZE",
            "outcome": "SUCCEEDED",
        }
    ).encode()


def test_service_jwt_cannot_replace_the_webhook_signature() -> None:
    """A perfectly valid Service JWT is not a provider signature."""
    with client() as api:
        response = api.post(
            CALLBACK_PATH, content=callback_body(), headers=auth_header()
        )
    assert response.status_code in {400, 401, 422}
    assert response.status_code != 200


def test_webhook_signature_cannot_replace_the_service_jwt() -> None:
    """A valid provider signature must not open an internal payment command."""
    settings = build_settings()
    body = callback_body()
    timestamp = str(int(time.time()))
    signature = callback_signature(settings.provider_callback_secret, timestamp, body)
    with client() as api:
        response = api.get(
            PAYMENT_PATH,
            headers={
                "X-Webhook-Timestamp": timestamp,
                "X-Webhook-Signature": f"sha256={signature}",
            },
        )
    assert response.status_code == 401


def test_callback_without_any_signature_is_rejected() -> None:
    with client() as api:
        response = api.post(CALLBACK_PATH, content=callback_body())
    assert response.status_code != 200
