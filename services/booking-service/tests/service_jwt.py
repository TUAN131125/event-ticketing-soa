"""Shared Service JWT test material for the Booking suites.

One RSA keypair is generated per test session and reused, so no suite invents its own key
handling and no production key is ever involved. Tokens are minted with the production
`ServiceJwtSigner` so the tests exercise the real issuing path.
"""

from __future__ import annotations

import base64
from functools import lru_cache

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from libs.platform_security import (
    ServiceJwtSigningSettings,
    ServiceJwtValidationSettings,
)

ISSUER = "event-ticketing-internal"
AUDIENCE = "booking-service"
CALLER = "booking-orchestrator"
KEY_ID = "test-internal-1"
ALLOWED_SUBJECTS = frozenset({CALLER})


@lru_cache(maxsize=1)
def _keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return (
        base64.b64encode(private_pem).decode(),
        base64.b64encode(public_pem).decode(),
    )


def private_key_base64() -> str:
    return _keypair()[0]


def public_key_base64() -> str:
    return _keypair()[1]


def validation_settings(
    *,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    allowed_subjects: frozenset[str] = ALLOWED_SUBJECTS,
) -> ServiceJwtValidationSettings:
    return ServiceJwtValidationSettings(
        None,
        public_key_base64(),
        issuer,
        audience,
        allowed_subjects,
    )


def signing_settings(
    *,
    issuer: str = ISSUER,
    subject: str = CALLER,
    key_id: str = KEY_ID,
    ttl_seconds: int = 60,
) -> ServiceJwtSigningSettings:
    return ServiceJwtSigningSettings(
        None,
        private_key_base64(),
        issuer,
        subject,
        key_id,
        ttl_seconds,
    )


def issue_token(audience: str = AUDIENCE, **signer_overrides) -> str:
    """Mint a token with the production signer."""
    return signing_settings(**signer_overrides).signer().issue(audience)


def auth_header(audience: str = AUDIENCE, **signer_overrides) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(audience, **signer_overrides)}"}
