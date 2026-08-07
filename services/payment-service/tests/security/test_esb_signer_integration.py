"""The ESB's production signer must be accepted by this service's production verifier.

Both sides are the real classes from libs.platform_security — the same code the ESB uses to
issue and the same code app/main.py wires as the verifier. Only the keypair is test material.
"""

from __future__ import annotations

import jwt
import pytest
from libs.platform_security import ServiceAuthenticationError

from tests.factories import build_settings
from tests.service_jwt import AUDIENCE, CALLER, ISSUER, KEY_ID, signing_settings


def esb_signer():
    """Exactly how the ESB builds its signer: ServiceJwtSigningSettings(...).signer()."""
    return signing_settings(subject=CALLER).signer()


def verifier():
    return build_settings().service_jwt.verifier()


def test_esb_signed_token_is_accepted_by_the_service_verifier() -> None:
    token = esb_signer().issue(AUDIENCE)
    principal = verifier().verify_authorization(f"Bearer {token}")
    assert principal.subject == CALLER
    assert "SERVICE" in principal.roles
    assert principal.token_id


def test_esb_token_carries_the_expected_header_and_claims() -> None:
    token = esb_signer().issue(AUDIENCE)
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "RS256"
    assert header["kid"] == KEY_ID
    claims = jwt.decode(token, options={"verify_signature": False}, audience=AUDIENCE)
    assert claims["iss"] == ISSUER
    assert claims["sub"] == CALLER
    assert claims["aud"] == AUDIENCE
    assert claims["roles"] == ["SERVICE"]
    assert claims["exp"] > claims["iat"]
    assert claims["jti"]


def test_a_token_minted_for_payment_is_rejected_here() -> None:
    """Cross-audience reuse must fail; audiences are not interchangeable."""
    token = esb_signer().issue("booking-service")
    with pytest.raises(ServiceAuthenticationError):
        verifier().verify_authorization(f"Bearer {token}")


def test_a_replayed_token_is_rejected() -> None:
    token = esb_signer().issue(AUDIENCE)
    shared = verifier()
    shared.verify_authorization(f"Bearer {token}")
    with pytest.raises(ServiceAuthenticationError):
        shared.verify_authorization(f"Bearer {token}")
