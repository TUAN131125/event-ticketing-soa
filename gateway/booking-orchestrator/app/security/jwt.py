from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

from app.domain.errors import AuthenticationFailed
from app.domain.models import Principal


class JwksVerifier:
    def __init__(
        self,
        url: str,
        issuer: str,
        audience: str,
        cache_seconds: int,
        client: httpx.AsyncClient,
        algorithm: str = "RS256",
    ) -> None:
        (
            self.url,
            self.issuer,
            self.audience,
            self.cache_seconds,
            self.client,
            self.algorithm,
        ) = (
            url,
            issuer,
            audience,
            cache_seconds,
            client,
            algorithm,
        )
        self._keys: dict[str, Any] = {}
        self._expires = 0.0
        self._lock = asyncio.Lock()

    async def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != self.algorithm or not header.get("kid"):
                raise AuthenticationFailed()
            key = await self._key(str(header["kid"]), False)
            if key is None:
                key = await self._key(str(header["kid"]), True)
            if key is None:
                raise AuthenticationFailed()
            claims = jwt.decode(
                token,
                key=key,
                algorithms=[self.algorithm],
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["sub", "roles", "iss", "aud", "iat", "exp"]},
            )
            roles = claims.get("roles")
            if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
                raise AuthenticationFailed()
            return Principal(str(claims["sub"]), tuple(roles))
        except AuthenticationFailed:
            raise
        except Exception as exc:
            raise AuthenticationFailed() from exc

    async def _key(self, kid: str, force: bool) -> Any | None:
        async with self._lock:
            if force or time.monotonic() >= self._expires:
                response = await self.client.get(self.url, timeout=2.0)
                response.raise_for_status()
                payload = response.json()
                self._keys = {
                    str(item["kid"]): RSAAlgorithm.from_jwk(json.dumps(item)) for item in payload.get("keys", []) if item.get("kid")
                }
                self._expires = time.monotonic() + self.cache_seconds
            return self._keys.get(kid)


class JwtSigner:
    def __init__(
        self,
        private_key: str,
        issuer: str,
        subject: str,
        key_id: str,
        ttl_seconds: int = 60,
    ) -> None:
        self.private_key, self.issuer, self.subject, self.key_id, self.ttl_seconds = (
            private_key,
            issuer,
            subject,
            key_id,
            ttl_seconds,
        )

    def service_token(self, audience: str) -> str:
        now = int(datetime.now(timezone.utc).timestamp())
        return jwt.encode(
            {
                "iss": self.issuer,
                "sub": self.subject,
                "aud": audience,
                "iat": now,
                "exp": now + self.ttl_seconds,
                "jti": str(uuid4()),
            },
            self.private_key,
            algorithm="RS256",
            headers={"kid": self.key_id},
        )


class WebSocketTicketIssuer:
    def __init__(
        self,
        private_key: str,
        issuer: str,
        audience: str,
        key_id: str,
        ttl_seconds: int,
    ) -> None:
        self.private_key, self.issuer, self.audience, self.key_id, self.ttl_seconds = (
            private_key,
            issuer,
            audience,
            key_id,
            ttl_seconds,
        )

    def issue(self, subject: str, booking_id: str) -> tuple[str, datetime]:
        now = int(datetime.now(timezone.utc).timestamp())
        expires = now + min(self.ttl_seconds, 60)
        claims: dict[str, Any] = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": subject,
            "bookingId": booking_id,
            "scope": "booking:status:read",
            "iat": now,
            "exp": expires,
            "jti": str(uuid4()),
        }
        token = jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": self.key_id})
        return token, datetime.fromtimestamp(expires, timezone.utc)
