"""Stable service errors safe for external responses."""

from __future__ import annotations

from typing import Any


class ServiceError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status: int,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = status
        self.retryable = retryable
        self.details = details or {}


class Unauthenticated(ServiceError):
    def __init__(self) -> None:
        super().__init__("UNAUTHENTICATED", "Authentication is required", 401)


class Forbidden(ServiceError):
    def __init__(self, message: str = "Access is denied") -> None:
        super().__init__("FORBIDDEN", message, 403)


class InvalidRequest(ServiceError):
    def __init__(self, message: str = "Request is invalid") -> None:
        super().__init__("INVALID_REQUEST", message, 422)


class RequestTooLarge(ServiceError):
    def __init__(self) -> None:
        super().__init__("REQUEST_TOO_LARGE", "Request body exceeds the configured limit", 413)


class PublishUnavailable(ServiceError):
    def __init__(self) -> None:
        super().__init__(
            "BROADCAST_UNAVAILABLE",
            "Status transport is temporarily unavailable",
            503,
            retryable=True,
        )
