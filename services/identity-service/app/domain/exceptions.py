"""Safe, stable errors exposed by the Identity API."""

from __future__ import annotations

from typing import Any


class IdentityError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        http_status: int,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retryable = retryable
        self.details = details or {}


class EmailAlreadyExists(IdentityError):
    def __init__(self) -> None:
        super().__init__("EMAIL_ALREADY_EXISTS", "Email is already registered", 409)


class InvalidCredentials(IdentityError):
    def __init__(self) -> None:
        super().__init__("INVALID_CREDENTIALS", "Email or password is invalid", 401)


class AccountDisabled(IdentityError):
    def __init__(self) -> None:
        super().__init__("ACCOUNT_DISABLED", "Account is disabled", 403)


class AccountLocked(IdentityError):
    def __init__(self, retry_after: int) -> None:
        super().__init__(
            "ACCOUNT_LOCKED",
            "Account is temporarily locked",
            423,
            details={"retryAfterSeconds": max(1, retry_after)},
        )


class RateLimited(IdentityError):
    def __init__(self, retry_after: int) -> None:
        super().__init__(
            "RATE_LIMITED",
            "Too many authentication attempts",
            429,
            details={"retryAfterSeconds": max(1, retry_after)},
        )


class Unauthenticated(IdentityError):
    def __init__(self) -> None:
        super().__init__("UNAUTHENTICATED", "Authentication is required", 401)


class TokenExpired(IdentityError):
    def __init__(self) -> None:
        super().__init__("TOKEN_EXPIRED", "Access token has expired", 401)


class TokenRevoked(IdentityError):
    def __init__(self) -> None:
        super().__init__("TOKEN_REVOKED", "Access token is no longer valid", 401)


class InvalidRefreshToken(IdentityError):
    def __init__(self) -> None:
        super().__init__(
            "INVALID_REFRESH_TOKEN", "Refresh token is invalid or expired", 401
        )


class RefreshTokenReuseDetected(IdentityError):
    def __init__(self) -> None:
        super().__init__(
            "REFRESH_TOKEN_REUSE_DETECTED",
            "Refresh token reuse was detected; the session family was revoked",
            401,
        )


class Forbidden(IdentityError):
    def __init__(self, message: str = "Permission denied") -> None:
        super().__init__("FORBIDDEN", message, 403)


class RoleNotFound(IdentityError):
    def __init__(self) -> None:
        super().__init__("ROLE_NOT_FOUND", "Role does not exist", 404)


class UserNotFound(IdentityError):
    def __init__(self) -> None:
        super().__init__("USER_NOT_FOUND", "User does not exist", 404)


class InvalidRequest(IdentityError):
    def __init__(self, message: str = "Request is invalid") -> None:
        super().__init__("INVALID_REQUEST", message, 400)


class DependencyUnavailable(IdentityError):
    def __init__(self) -> None:
        super().__init__(
            "DEPENDENCY_UNAVAILABLE",
            "Identity data store is temporarily unavailable",
            503,
            retryable=True,
        )
