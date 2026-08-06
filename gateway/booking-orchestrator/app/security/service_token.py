from __future__ import annotations

import time
import uuid
from pathlib import Path

import jwt


class ServiceTokenProvider:
    """Create a fresh short-lived internal service token for each attempt.

    RS256 is used when a private key is configured. A pre-issued static token is
    accepted only as a local compatibility fallback.
    """

    def __init__(
        self,
        *,
        private_key: str | None = None,
        static_token: str = "",
        issuer: str = "booking-orchestrator",
        subject: str = "booking-orchestrator",
        key_id: str = "esb-internal-1",
        ttl_seconds: int = 60,
    ) -> None:
        self.private_key = private_key
        self.static_token = static_token
        self.issuer = issuer
        self.subject = subject
        self.key_id = key_id
        self.ttl_seconds = ttl_seconds

    def token(self, audience: str) -> str:
        if self.private_key:
            now = int(time.time())
            return jwt.encode(
                {
                    "iss": self.issuer,
                    "sub": self.subject,
                    "aud": audience,
                    "roles": ["SERVICE"],
                    "iat": now,
                    "exp": now + self.ttl_seconds,
                    "jti": str(uuid.uuid4()),
                },
                self.private_key,
                algorithm="RS256",
                headers={"kid": self.key_id},
            )
        return self.static_token


def load_optional_secret(value: str | None, path: Path | None, name: str) -> str | None:
    if value and path:
        raise ValueError(f"configure only one of {name} or {name}_PATH")
    if value:
        return value
    if path is None:
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {name}_PATH: {path}") from exc
    if not content.strip():
        raise ValueError(f"{name}_PATH is empty: {path}")
    return content
