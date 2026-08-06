"""Internal callers are authenticated before any booking data is exposed."""

import secrets

from app.domain.exceptions import AuthenticationFailed


def authenticate_service(provided: str | None, expected: str) -> None:
    if not provided or not secrets.compare_digest(provided, expected):
        raise AuthenticationFailed()
