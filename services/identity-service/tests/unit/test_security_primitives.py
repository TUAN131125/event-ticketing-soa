from __future__ import annotations

from dataclasses import replace

import jwt
import pytest

from app.domain.exceptions import InvalidRequest, TokenExpired, Unauthenticated
from app.domain.rules import normalize_email, validate_password
from app.security.passwords import PasswordService
from app.security.tokens import TokenService


def test_password_hash_is_argon2_and_verifies(unit_settings):
    passwords = PasswordService(unit_settings)
    encoded = passwords.hash("Correct-Horse-9!Long")
    assert encoded.startswith("$argon2id$")
    assert passwords.verify(encoded, "Correct-Horse-9!Long")
    assert not passwords.verify(encoded, "not-the-password")


def test_password_policy_rejects_weak_values():
    with pytest.raises(InvalidRequest):
        validate_password("short")
    with pytest.raises(InvalidRequest):
        validate_password("alllowercase1234")


def test_email_normalization_is_case_insensitive():
    display, normalized = normalize_email(" Customer@Example.COM ")
    assert display == "Customer@example.com"
    assert normalized == "customer@example.com"


def test_rs256_token_claims_and_jwks(unit_settings):
    tokens = TokenService(unit_settings)
    encoded = tokens.issue_access_token(
        user_id="user-1", roles=("CUSTOMER",), token_version=1
    )
    principal = tokens.decode_access_token(encoded)
    assert principal.user_id == "user-1"
    assert principal.roles == ("CUSTOMER",)
    unverified = jwt.decode(encoded, options={"verify_signature": False})
    assert unverified["iss"] == "http://localhost:8009"
    assert unverified["aud"] == "public-esb"
    assert unverified["sub"] == "user-1"
    assert isinstance(unverified["jti"], str)
    assert unverified["tokenVersion"] == 1
    assert "customerId" not in unverified
    key = tokens.jwks()["keys"][0]
    assert key["alg"] == "RS256"
    assert key["kid"] == unit_settings.key_id
    assert jwt.get_unverified_header(encoded)["kid"] == unit_settings.key_id


def test_token_rejects_wrong_audience(unit_settings):
    tokens = TokenService(unit_settings)
    encoded = tokens.issue_access_token(
        user_id="user-1", roles=("CUSTOMER",), token_version=1
    )
    altered = replace(unit_settings, audience="another-api")
    with pytest.raises(Unauthenticated):
        TokenService(altered).decode_access_token(encoded)


def test_expired_token_is_distinguished(unit_settings):
    tokens = TokenService(unit_settings)
    import datetime

    encoded = tokens.issue_access_token(
        user_id="user-1",
        roles=("CUSTOMER",),
        token_version=1,
        now=datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=10_000),
    )
    with pytest.raises(TokenExpired):
        tokens.decode_access_token(encoded)
