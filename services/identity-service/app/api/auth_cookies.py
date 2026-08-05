"""HTTP-only refresh-cookie and CSRF-cookie helpers."""

from fastapi import Response

from app.config import Settings
from app.security.csrf import CSRF_COOKIE, REFRESH_COOKIE


def set_auth_cookies(
    response: Response,
    settings: Settings,
    *,
    refresh_token: str,
    csrf_token: str,
    max_age: int,
) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/auth",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/auth",
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/auth",
    )
    response.delete_cookie(
        CSRF_COOKIE,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/auth",
    )


def disable_token_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
