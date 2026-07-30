"""Double-submit CSRF protection for refresh-token cookie endpoints."""

from __future__ import annotations

import secrets

from fastapi import Request

from app.config import Settings
from app.domain.exceptions import Forbidden

REFRESH_COOKIE = "identity_refresh"
CSRF_COOKIE = "identity_csrf"
CSRF_HEADER = "X-CSRF-Token"


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_cookie_request(request: Request, settings: Settings) -> None:
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise Forbidden("CSRF validation failed")
    origin = request.headers.get("Origin")
    if origin and origin.rstrip("/") not in settings.allowed_origins:
        raise Forbidden("Request origin is not allowed")
