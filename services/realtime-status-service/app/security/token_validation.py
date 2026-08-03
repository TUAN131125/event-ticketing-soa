"""Strict RS256 JWT verification using a bounded-TTL JWKS cache."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import jwt
from jwt import InvalidTokenError, PyJWTError
from jwt.algorithms import RSAAlgorithm

from app.config import Settings
from app.errors import Unauthenticated


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    subject: str
    roles: frozenset[str]
    token_id: str
    customer_id: str | None = None


class TokenValidator(Protocol):
    async def validate(self, token: str) -> AuthenticatedPrincipal: ...


class JwksTokenValidator:
    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._client = client
        self._clock = clock
        self._keys: dict[str, Any] = {}
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def _refresh(self, *, force: bool = False) -> None:
        async with self._lock:
            if not force and self._keys and self._clock() < self._expires_at:
                return
            owns_client = self._client is None
            client = self._client or httpx.AsyncClient(timeout=self._settings.jwks_timeout_seconds)
            try:
                response = await client.get(
                    self._settings.jwks_url, headers={"Accept": "application/jwk-set+json"}
                )
                response.raise_for_status()
                payload = response.json()
                keys = payload.get("keys") if isinstance(payload, dict) else None
                if not isinstance(keys, list):
                    raise ValueError("invalid JWKS")
                parsed: dict[str, Any] = {}
                for item in keys:
                    if not isinstance(item, dict):
                        continue
                    kid = item.get("kid")
                    if (
                        isinstance(kid, str)
                        and item.get("kty") == "RSA"
                        and item.get("alg") in {None, self._settings.jwt_algorithm}
                        and item.get("use") in {None, "sig"}
                    ):
                        parsed[kid] = RSAAlgorithm.from_jwk(json.dumps(item))
                if not parsed:
                    raise ValueError("JWKS contains no usable signing keys")
                self._keys = parsed
                self._expires_at = self._clock() + self._settings.jwks_cache_ttl_seconds
            except (
                httpx.HTTPError,
                PyJWTError,
                ValueError,
                TypeError,
                json.JSONDecodeError,
            ) as exc:
                raise Unauthenticated() from exc
            finally:
                if owns_client:
                    await client.aclose()

    async def validate(self, token: str) -> AuthenticatedPrincipal:
        if not token or len(token) > 8192:
            raise Unauthenticated()
        try:
            header = jwt.get_unverified_header(token)
        except InvalidTokenError as exc:
            raise Unauthenticated() from exc
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid or header.get("alg") != self._settings.jwt_algorithm:
            raise Unauthenticated()
        if not self._keys or self._clock() >= self._expires_at:
            await self._refresh()
        key = self._keys.get(kid)
        if key is None:
            await self._refresh(force=True)
            key = self._keys.get(kid)
        if key is None:
            raise Unauthenticated()
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=[self._settings.jwt_algorithm],
                issuer=self._settings.jwt_issuer,
                audience=self._settings.jwt_audience,
                options={"require": ["iss", "aud", "sub", "exp", "iat", "jti", "roles"]},
            )
        except InvalidTokenError as exc:
            raise Unauthenticated() from exc
        subject = claims.get("sub")
        token_id = claims.get("jti")
        roles = claims.get("roles")
        customer_id = claims.get("customerId")
        if (
            not isinstance(subject, str)
            or not subject
            or len(subject) > 128
            or not isinstance(token_id, str)
            or not token_id
            or not isinstance(roles, list)
            or not all(isinstance(role, str) and 0 < len(role) <= 64 for role in roles)
            or (customer_id is not None and (not isinstance(customer_id, str) or not customer_id))
        ):
            raise Unauthenticated()
        return AuthenticatedPrincipal(subject, frozenset(roles), token_id, customer_id)


def websocket_token(
    headers: Any, query_params: Any, *, allow_query: bool
) -> tuple[str | None, str | None]:
    """Return token and accepted subprotocol without logging either source."""
    authorization = headers.get("authorization")
    if isinstance(authorization, str) and authorization.startswith("Bearer "):
        return authorization[7:].strip(), None
    raw_protocols = headers.get("sec-websocket-protocol")
    if isinstance(raw_protocols, str):
        protocols = [item.strip() for item in raw_protocols.split(",")]
        if len(protocols) == 2 and protocols[0].lower() == "bearer":
            return protocols[1], "bearer"
    if allow_query:
        token = query_params.get("access_token")
        if isinstance(token, str):
            return token, None
    return None, None
