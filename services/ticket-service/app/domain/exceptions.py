"""Stable domain errors exposed by Ticket Service."""

from __future__ import annotations

from typing import Any


class TicketError(Exception):
    code = "TICKET_ERROR"
    http_status = 400
    retryable = False

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidRequest(TicketError):
    code = "INVALID_REQUEST"


class AuthenticationFailed(TicketError):
    code = "AUTHENTICATION_FAILED"
    http_status = 401

    def __init__(self) -> None:
        super().__init__("Internal service authentication failed")


class Forbidden(TicketError):
    code = "FORBIDDEN"
    http_status = 403

    def __init__(
        self, message: str = "Caller cannot perform this ticket operation"
    ) -> None:
        super().__init__(message)


class TicketNotFound(TicketError):
    code = "TICKET_NOT_FOUND"
    http_status = 404

    def __init__(self, ticket_id: str) -> None:
        super().__init__(
            f"Ticket {ticket_id} was not found", details={"ticketId": ticket_id}
        )


class InvalidStateTransition(TicketError):
    code = "INVALID_STATE_TRANSITION"
    http_status = 409

    def __init__(self, current: str, target: str) -> None:
        super().__init__(
            f"Ticket cannot transition from {current} to {target}",
            details={"currentStatus": current, "targetStatus": target},
        )


class VersionConflict(TicketError):
    code = "VERSION_CONFLICT"
    http_status = 409

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(
            "Ticket resource version does not match",
            details={"expectedVersion": expected, "actualVersion": actual},
        )


class IdempotencyConflict(TicketError):
    code = "IDEMPOTENCY_CONFLICT"
    http_status = 409

    def __init__(self) -> None:
        super().__init__("Idempotency key was already used for another request")


class BookingTicketConflict(TicketError):
    code = "BOOKING_TICKET_CONFLICT"
    http_status = 409

    def __init__(self, booking_id: str) -> None:
        super().__init__(
            f"Booking {booking_id} already has another ticket definition",
            details={"bookingId": booking_id},
        )


class SeatTicketConflict(TicketError):
    code = "SEAT_TICKET_CONFLICT"
    http_status = 409

    def __init__(self, event_id: str, seat_id: str) -> None:
        super().__init__(
            "Event seat is already attached to another ticket",
            details={"eventId": event_id, "seatId": seat_id},
        )


class InvalidQrToken(TicketError):
    code = "INVALID_QR_TOKEN"
    http_status = 409

    def __init__(self) -> None:
        super().__init__("QR token is invalid, stale or belongs to another ticket")


class AlreadyCheckedIn(TicketError):
    code = "TICKET_ALREADY_CHECKED_IN"
    http_status = 409

    def __init__(self, *, checked_in_at: str, gate_id: str) -> None:
        super().__init__(
            "Ticket has already been checked in",
            details={"checkedInAt": checked_in_at, "gateId": gate_id},
        )


class DependencyUnavailable(TicketError):
    code = "DEPENDENCY_UNAVAILABLE"
    http_status = 503
    retryable = True

    def __init__(self) -> None:
        super().__init__("Ticket persistence is temporarily unavailable")


class InternalFailure(TicketError):
    code = "INTERNAL_ERROR"
    http_status = 500

    def __init__(self) -> None:
        super().__init__("Ticket Service could not complete the request")
