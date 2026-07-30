"""Stable domain errors mapped to SOAP Faults and admin HTTP responses."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(eq=False)
class SeatInventoryError(Exception):
    code: str
    message: str
    retryable: bool = False
    http_status: int = 409

    def __str__(self) -> str:
        return self.message


class InvalidRequest(SeatInventoryError):
    def __init__(self, message: str = "The request is invalid") -> None:
        super().__init__("INVALID_REQUEST", message, False, 400)


class AuthenticationFailed(SeatInventoryError):
    def __init__(self) -> None:
        super().__init__(
            "AUTHENTICATION_FAILED", "Service authentication failed", False, 401
        )


class EventNotFound(SeatInventoryError):
    def __init__(self, event_id: str) -> None:
        super().__init__(
            "EVENT_NOT_FOUND",
            f"Inventory for event {event_id} was not found",
            False,
            404,
        )


class SeatNotFound(SeatInventoryError):
    def __init__(self, seat_ids: list[str] | tuple[str, ...]) -> None:
        joined = ", ".join(sorted(seat_ids))
        super().__init__("SEAT_NOT_FOUND", f"Seat(s) not found: {joined}", False, 404)


class SeatUnavailable(SeatInventoryError):
    def __init__(self, seat_ids: list[str] | tuple[str, ...]) -> None:
        joined = ", ".join(sorted(seat_ids))
        super().__init__(
            "SEAT_UNAVAILABLE", f"Seat(s) are unavailable: {joined}", False, 409
        )


class ReservationNotFound(SeatInventoryError):
    def __init__(self, reservation_id: str) -> None:
        super().__init__(
            "RESERVATION_NOT_FOUND",
            f"Reservation {reservation_id} was not found",
            False,
            404,
        )


class ReservationExpired(SeatInventoryError):
    def __init__(self, reservation_id: str) -> None:
        super().__init__(
            "RESERVATION_EXPIRED",
            f"Reservation {reservation_id} has expired",
            False,
            409,
        )


class InvalidReservationState(SeatInventoryError):
    def __init__(self, reservation_id: str, state: str) -> None:
        super().__init__(
            "INVALID_RESERVATION_STATE",
            f"Reservation {reservation_id} cannot be changed from state {state}",
            False,
            409,
        )


class VersionConflict(SeatInventoryError):
    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(
            "VERSION_CONFLICT",
            f"Expected resource version {expected}, current version is {actual}",
            False,
            409,
        )


class IdempotencyConflict(SeatInventoryError):
    def __init__(self) -> None:
        super().__init__(
            "IDEMPOTENCY_KEY_REUSED",
            "The idempotency key was already used with a different request",
            False,
            409,
        )


class InventoryConflict(SeatInventoryError):
    def __init__(self, message: str) -> None:
        super().__init__("INVENTORY_CONFLICT", message, False, 409)


class DependencyUnavailable(SeatInventoryError):
    def __init__(self) -> None:
        super().__init__(
            "DEPENDENCY_UNAVAILABLE",
            "Seat inventory storage is temporarily unavailable",
            True,
            503,
        )


class InternalFailure(SeatInventoryError):
    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "The seat inventory operation could not be completed",
            False,
            500,
        )
