"""Stable domain errors exposed by Booking Service."""

from __future__ import annotations

from typing import Any


class BookingError(Exception):
    code = "BOOKING_ERROR"
    http_status = 400
    retryable = False

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidRequest(BookingError):
    code = "INVALID_REQUEST"


class AuthenticationFailed(BookingError):
    code = "AUTHENTICATION_FAILED"
    http_status = 401

    def __init__(self) -> None:
        super().__init__("Internal service authentication failed")


class BookingNotFound(BookingError):
    code = "BOOKING_NOT_FOUND"
    http_status = 404

    def __init__(self, booking_id: str) -> None:
        super().__init__(
            f"Booking {booking_id} was not found",
            details={"bookingId": booking_id},
        )


class InvalidStateTransition(BookingError):
    code = "INVALID_STATE_TRANSITION"
    http_status = 409

    def __init__(self, current: str, target: str) -> None:
        super().__init__(
            f"Booking cannot transition from {current} to {target}",
            details={"currentStatus": current, "targetStatus": target},
        )


class VersionConflict(BookingError):
    code = "VERSION_CONFLICT"
    http_status = 409

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(
            "Booking resource version does not match",
            details={"expectedVersion": expected, "actualVersion": actual},
        )


class IdempotencyConflict(BookingError):
    code = "IDEMPOTENCY_CONFLICT"
    http_status = 409

    def __init__(self) -> None:
        super().__init__("Idempotency key was already used for another request")


class ReservationConflict(BookingError):
    code = "RESERVATION_CONFLICT"
    http_status = 409

    def __init__(self, reservation_id: str) -> None:
        super().__init__(
            f"Reservation {reservation_id} is already attached to another booking",
            details={"reservationId": reservation_id},
        )


class DependencyUnavailable(BookingError):
    code = "DEPENDENCY_UNAVAILABLE"
    http_status = 503
    retryable = True

    def __init__(self) -> None:
        super().__init__("Booking persistence is temporarily unavailable")


class InternalFailure(BookingError):
    code = "INTERNAL_ERROR"
    http_status = 500

    def __init__(self) -> None:
        super().__init__("Booking Service could not complete the request")
