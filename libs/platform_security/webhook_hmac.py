"""HMAC request signing with bounded timestamp and replay protection."""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from datetime import datetime


class HmacAuthenticationError(ValueError):
    """Raised for an invalid, stale or replayed signed request."""


def sign_hmac_request(secret: str | bytes, timestamp: str, body: bytes) -> str:
    key = secret.encode("utf-8") if isinstance(secret, str) else secret
    return hmac.new(
        key, timestamp.encode("ascii") + b"." + body, hashlib.sha256
    ).hexdigest()


class HmacRequestVerifier:
    def __init__(self, secret: str | bytes, *, tolerance_seconds: int = 300) -> None:
        self._secret = secret.encode("utf-8") if isinstance(secret, str) else secret
        if not self._secret:
            raise ValueError("HMAC secret is required")
        self._tolerance_seconds = tolerance_seconds
        self._seen: dict[str, int] = {}
        self._lock = threading.Lock()

    def verify(
        self, *, timestamp: str | None, signature: str | None, body: bytes
    ) -> None:
        if not timestamp or not signature:
            raise HmacAuthenticationError("HMAC timestamp and signature are required")
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            offset = parsed.utcoffset()
            if offset is None or offset.total_seconds() != 0:
                raise ValueError
            timestamp_value = int(parsed.timestamp())
        except ValueError as exc:
            raise HmacAuthenticationError("HMAC timestamp is invalid") from exc
        now = int(time.time())
        if abs(now - timestamp_value) > self._tolerance_seconds:
            raise HmacAuthenticationError("HMAC timestamp is stale")
        expected = sign_hmac_request(self._secret, timestamp, body)
        if not hmac.compare_digest(expected, signature.removeprefix("sha256=")):
            raise HmacAuthenticationError("HMAC signature is invalid")
        replay_key = f"{timestamp}:{signature}"
        with self._lock:
            self._seen = {
                key: expiry for key, expiry in self._seen.items() if expiry >= now
            }
            if replay_key in self._seen:
                raise HmacAuthenticationError("HMAC request replay detected")
            self._seen[replay_key] = now + self._tolerance_seconds
