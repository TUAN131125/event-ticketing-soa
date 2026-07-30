"""Constant-time service-to-service token validation."""

from __future__ import annotations

import hmac

from app.domain.exceptions import AuthenticationFailed


def authenticate_service(provided: str | None, expected: str) -> None:
    if not provided or not hmac.compare_digest(provided, expected):
        raise AuthenticationFailed()
