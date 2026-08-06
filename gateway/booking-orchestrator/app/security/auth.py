from __future__ import annotations

import asyncio
from typing import Any

import jwt

from app.domain.errors import EsbError
from app.domain.models import Principal


class JwtVerifier:
    """Verify browser JWTs with JWKS (preferred) or an explicitly configured HS256 secret."""

    def __init__(self, issuer: str = "", audience: str = "", jwks_url: str = "", shared_secret: str = ""):
        self.issuer = issuer or None
        self.audience = audience or None
        self.jwks_url = jwks_url
        self.shared_secret = shared_secret
        self._jwks = jwt.PyJWKClient(jwks_url) if jwks_url else None

    async def verify(self, authorization: str | None) -> Principal:
        if not authorization or not authorization.startswith("Bearer "):
            raise EsbError("UNAUTHORIZED", "Bearer token is required", 401)
        token = authorization[7:]
        try:
            payload = await asyncio.to_thread(self._decode, token)
            subject = str(payload["sub"])
            roles: Any = payload.get("roles", payload.get("role", []))
            if isinstance(roles, str):
                roles = [roles]
            return Principal(subject, frozenset(map(str, roles)), payload.get("customerId"))
        except EsbError:
            raise
        except Exception as exc:
            raise EsbError("UNAUTHORIZED", "Invalid access token", 401) from exc

    def _decode(self, token: str) -> dict[str, Any]:
        options = {"require": ["sub", "exp"]}
        kwargs: dict[str, Any] = {
            "algorithms": ["RS256", "ES256"] if self._jwks else ["HS256"],
            "audience": self.audience,
            "issuer": self.issuer,
            "options": options,
        }
        if self._jwks:
            key = self._jwks.get_signing_key_from_jwt(token).key
        elif self.shared_secret:
            key = self.shared_secret
        else:
            raise EsbError("ESB_SECURITY_MISCONFIGURED", "Configure ESB_JWKS_URL or ESB_JWT_SHARED_SECRET", 503)
        return jwt.decode(token, key=key, **kwargs)
