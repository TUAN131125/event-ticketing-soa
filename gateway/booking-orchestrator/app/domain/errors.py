from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EsbError(Exception):
    code: str
    message: str
    status_code: int = 503
    retryable: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.code


class AccessDenied(EsbError):
    def __init__(self, code: str = "ACCESS_DENIED", message: str = "Access denied.") -> None:
        super().__init__(code, message, 403, False)


class AuthenticationFailed(EsbError):
    def __init__(self, message: str = "Authentication required.") -> None:
        super().__init__("AUTHENTICATION_REQUIRED", message, 401, False)


class IdempotencyConflict(EsbError):
    def __init__(self) -> None:
        super().__init__(
            "IDEMPOTENCY_KEY_REUSED",
            "Idempotency key was used with a different request.",
            409,
            False,
        )


class BusinessFault(EsbError):
    pass


class DependencyFailure(EsbError):
    pass


class AmbiguousOutcome(DependencyFailure):
    def __init__(self, operation: str) -> None:
        super().__init__(
            "DEPENDENCY_OUTCOME_UNKNOWN",
            "A dependency outcome is being reconciled.",
            503,
            True,
            {"operation": operation},
        )


class CommandNotDispatched(DependencyFailure):
    """The command was rejected before any byte reached the provider."""

    def __init__(self, operation: str, reason_code: str) -> None:
        super().__init__(
            "COMMAND_NOT_DISPATCHED",
            "The command was not sent to the dependency.",
            503,
            True,
            {"operation": operation, "reasonCode": reason_code},
        )
        self.reason_code = reason_code


class ProbeFailure(Exception):
    """A health probe outcome carrying only a stable, public-safe code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
