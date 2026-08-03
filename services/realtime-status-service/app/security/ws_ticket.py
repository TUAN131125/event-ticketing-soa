"""Validation for short-lived ESB-signed WebSocket tickets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from app.errors import Unauthenticated


@dataclass(frozen=True, slots=True)
class ValidatedWebSocketTicket:
    subject: str
    booking_id: str
    jti: str
    expires_at: int


class WebSocketTicketValidator(Protocol):
    async def validate(self, ticket: str, booking_id: str) -> ValidatedWebSocketTicket: ...


class SignedWebSocketTicketValidator:
    def __init__(
        self,
        *,
        public_key_path: Path,
        issuer: str,
        audience: str,
        key_id: str | None,
        max_ttl_seconds: int,
    ) -> None:
        try:
            key = serialization.load_pem_public_key(public_key_path.read_bytes())
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError("WebSocket ticket public key is invalid") from exc
        if not isinstance(key, RSAPublicKey):
            raise ValueError("WebSocket ticket public key must be RSA")
        self._key = key
        self._issuer = issuer
        self._audience = audience
        self._key_id = key_id
        self._max_ttl = max_ttl_seconds

    async def validate(self, ticket: str, booking_id: str) -> ValidatedWebSocketTicket:
        try:
            header = jwt.get_unverified_header(ticket)
            if header.get("alg") != "RS256":
                raise Unauthenticated()
            if self._key_id is not None and header.get("kid") != self._key_id:
                raise Unauthenticated()
            claims = jwt.decode(
                ticket,
                self._key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={
                    "require": ["iss", "aud", "sub", "bookingId", "scope", "iat", "exp", "jti"]
                },
            )
            issued_at = int(claims["iat"])
            expires_at = int(claims["exp"])
            subject = str(claims["sub"])
            claim_booking_id = str(claims["bookingId"])
            jti = str(claims["jti"])
            if not subject or not jti or claim_booking_id != booking_id:
                raise Unauthenticated()
            if claims["scope"] != "booking:status:read":
                raise Unauthenticated()
            if expires_at <= issued_at or expires_at - issued_at > self._max_ttl:
                raise Unauthenticated()
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            raise Unauthenticated() from exc
        return ValidatedWebSocketTicket(subject, claim_booking_id, jti, expires_at)
