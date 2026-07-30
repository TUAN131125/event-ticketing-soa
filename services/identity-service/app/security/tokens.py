"""RS256 access tokens, refresh-token primitives and JWKS publication."""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import (
    RSAPrivateKey,
    RSAPublicKey,
)
from jwt import ExpiredSignatureError, InvalidTokenError

from app.config import Settings
from app.domain.exceptions import TokenExpired, Unauthenticated
from app.domain.value_objects import Principal


def _base64url_uint(value: int) -> str:
    length = max(1, (value.bit_length() + 7) // 8)
    return base64.urlsafe_b64encode(value.to_bytes(length, "big")).rstrip(b"=").decode()


class TokenService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        private_key = serialization.load_pem_private_key(
            settings.private_key_path.read_bytes(), password=None
        )
        public_key = serialization.load_pem_public_key(
            settings.public_key_path.read_bytes()
        )
        if not isinstance(private_key, RSAPrivateKey) or not isinstance(
            public_key, RSAPublicKey
        ):
            raise ValueError("Identity signing keys must be RSA keys")
        if private_key.key_size < 2048:
            raise ValueError("Identity RSA signing key must be at least 2048 bits")
        if private_key.public_key().public_numbers() != public_key.public_numbers():
            raise ValueError("Identity private and public signing keys do not match")
        self._private_key = private_key
        self._public_key = public_key

    def issue_access_token(
        self,
        *,
        user_id: str,
        roles: tuple[str, ...],
        token_version: int,
        now: datetime | None = None,
    ) -> str:
        issued_at = now or datetime.now(UTC)
        payload: dict[str, Any] = {
            "iss": self._settings.issuer,
            "aud": self._settings.audience,
            "sub": user_id,
            "iat": issued_at,
            "exp": issued_at
            + timedelta(seconds=self._settings.access_token_ttl_seconds),
            "jti": str(uuid.uuid4()),
            "roles": list(roles),
            "tokenVersion": token_version,
        }
        return str(
            jwt.encode(
                payload,
                self._private_key,
                algorithm="RS256",
                headers={"kid": self._settings.key_id, "typ": "JWT"},
            )
        )

    def decode_access_token(self, token: str) -> Principal:
        try:
            payload = jwt.decode(
                token,
                self._public_key,
                algorithms=["RS256"],
                audience=self._settings.audience,
                issuer=self._settings.issuer,
                options={
                    "require": [
                        "iss",
                        "aud",
                        "sub",
                        "iat",
                        "exp",
                        "jti",
                        "roles",
                        "tokenVersion",
                    ]
                },
            )
        except ExpiredSignatureError as exc:
            raise TokenExpired() from exc
        except InvalidTokenError as exc:
            raise Unauthenticated() from exc
        roles = payload.get("roles")
        token_version = payload.get("tokenVersion")
        if (
            not isinstance(payload.get("sub"), str)
            or not isinstance(payload.get("jti"), str)
            or not isinstance(roles, list)
            or not all(isinstance(role, str) for role in roles)
            or not isinstance(token_version, int)
        ):
            raise Unauthenticated()
        return Principal(
            user_id=payload["sub"],
            roles=tuple(sorted(set(roles))),
            token_version=token_version,
            token_id=payload["jti"],
        )

    def jwks(self) -> dict[str, list[dict[str, str]]]:
        numbers = self._public_key.public_numbers()
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": self._settings.key_id,
                    "n": _base64url_uint(numbers.n),
                    "e": _base64url_uint(numbers.e),
                }
            ]
        }

    @staticmethod
    def generate_refresh_token() -> str:
        return secrets.token_urlsafe(64)

    @staticmethod
    def hash_refresh_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def user_agent_hash(user_agent: str | None) -> str | None:
        if not user_agent:
            return None
        return hashlib.sha256(user_agent.encode("utf-8")).hexdigest()
