from __future__ import annotations

import time
import uuid

import jwt

from app.domain.errors import Conflict, EsbError


class WebSocketTicketIssuer:
    def __init__(
        self,
        signing_secret: str,
        repository,
        issuer: str = "booking-orchestrator",
        audience: str = "realtime-status-service",
        ttl_seconds: int = 45,
        *,
        private_key: str | None = None,
        key_id: str = "esb-ws-1",
    ) -> None:
        self.signing_secret = signing_secret
        self.private_key = private_key
        self.key_id = key_id
        self.repository = repository
        self.issuer = issuer
        self.audience = audience
        self.ttl_seconds = min(ttl_seconds, 60)

    async def issue(
        self,
        booking_id: str,
        subject: str,
        idempotency_key: str,
    ) -> dict[str, str]:
        if not self.private_key and not self.signing_secret:
            raise EsbError(
                "ESB_SECURITY_MISCONFIGURED",
                "Configure an ESB WebSocket ticket signing key",
                503,
            )
        cache_key = f"{subject}:{idempotency_key}"
        existing = await self.repository.get_ws_ticket(cache_key)
        if existing:
            if existing["bookingId"] != booking_id:
                raise Conflict(
                    "IDEMPOTENCY_KEY_REUSED",
                    "Idempotency-Key was already used for another booking",
                )
            return existing

        now = int(time.time())
        expires = now + self.ttl_seconds
        claims = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": subject,
            "bookingId": booking_id,
            "scope": "booking:status:read",
            "iat": now,
            "exp": expires,
            "jti": str(uuid.uuid4()),
        }
        if self.private_key:
            token = jwt.encode(
                claims,
                self.private_key,
                algorithm="RS256",
                headers={"kid": self.key_id},
            )
        else:
            token = jwt.encode(claims, self.signing_secret, algorithm="HS256")

        from datetime import datetime, timezone

        response = {
            "ticket": token,
            "bookingId": booking_id,
            "expiresAt": datetime.fromtimestamp(expires, timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        }
        await self.repository.save_ws_ticket(cache_key, expires, response)
        return response
