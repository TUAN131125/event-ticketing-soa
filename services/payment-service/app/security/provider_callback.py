"""HMAC verification and replay protection for mock provider callbacks."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime

from app.domain.exceptions import ProviderSignatureInvalid


def callback_signature(secret: str, timestamp: str, body: bytes) -> str:
    message = timestamp.encode("utf-8") + b"." + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_callback(
    *,
    secret: str,
    timestamp: str | None,
    signature: str | None,
    body: bytes,
    replay_window_seconds: int,
    max_body_bytes: int,
    now: datetime | None = None,
) -> datetime:
    if not timestamp or not signature:
        raise ProviderSignatureInvalid("Provider callback headers are required")
    if len(body) > max_body_bytes:
        raise ProviderSignatureInvalid("Provider callback body is too large")
    try:
        parsed = datetime.fromtimestamp(int(timestamp), tz=UTC)
    except (TypeError, ValueError, OSError) as exc:
        raise ProviderSignatureInvalid(
            "Provider callback timestamp is invalid"
        ) from exc
    current = now or datetime.now(UTC)
    if abs((current - parsed).total_seconds()) > replay_window_seconds:
        raise ProviderSignatureInvalid(
            "Provider callback timestamp is outside replay window"
        )
    expected = callback_signature(secret, timestamp, body)
    normalized = signature.removeprefix("sha256=").strip().lower()
    if not hmac.compare_digest(expected, normalized):
        raise ProviderSignatureInvalid()
    return parsed
