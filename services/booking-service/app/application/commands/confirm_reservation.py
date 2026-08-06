"""Record authoritative ConfirmSeats evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy.orm import Session

from app.application.commands.transition import BookingTransition, execute_transition
from app.config import Settings
from app.domain.entities import Booking
from app.domain.enums import ReservationEvidenceStatus
from app.domain.exceptions import InvalidRequest
from app.domain.rules import validate_expected_version, validate_identifier
from app.domain.value_objects import RequestContext


@dataclass(frozen=True, slots=True)
class ConfirmReservation(BookingTransition):
    scope: ClassVar[str] = "ConfirmReservation"

    target_booking_id: str
    reservation_id: str
    expected_version: int
    reservation_version: int | None

    @classmethod
    def of(
        cls,
        *,
        booking_id: str,
        reservation_id: str,
        expected_version: int,
        reservation_version: int | None,
    ) -> "ConfirmReservation":
        return cls(
            target_booking_id=validate_identifier(booking_id, "bookingId"),
            reservation_id=validate_identifier(reservation_id, "reservationId"),
            expected_version=validate_expected_version(expected_version),
            reservation_version=reservation_version,
        )

    @property
    def booking_id(self) -> str:
        return self.target_booking_id

    def request_payload(self) -> dict[str, Any]:
        return {
            "bookingId": self.target_booking_id,
            "reservationId": self.reservation_id,
            "expectedVersion": self.expected_version,
            "reservationVersion": self.reservation_version,
        }

    def is_already_applied(self, booking: Booking) -> bool:
        if booking.reservation_id != self.reservation_id:
            raise InvalidRequest("reservationId does not match this booking")
        if booking.reservation_status not in {
            ReservationEvidenceStatus.CONFIRMED,
            ReservationEvidenceStatus.RELEASE_PENDING,
            ReservationEvidenceStatus.RELEASED,
        }:
            return False
        if self.reservation_version is not None:
            current_version = booking.reservation_version
            if current_version is None or current_version < self.reservation_version:
                raise InvalidRequest("Reservation version evidence does not match")
        return True

    def apply(self, booking: Booking, now: datetime) -> None:
        booking.confirm_reservation(
            reservation_id=self.reservation_id,
            expected_version=self.expected_version,
            reservation_version=self.reservation_version,
            now=now,
        )

    def audit_details(self, booking: Booking) -> dict[str, Any]:
        return {
            "reservationId": booking.reservation_id,
            "reservationStatus": booking.reservation_status.value,
            "reservationVersion": booking.reservation_version,
        }


def confirm_reservation(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    booking_id: str,
    reservation_id: str,
    expected_version: int,
    reservation_version: int | None = None,
) -> Booking:
    return execute_transition(
        session,
        settings,
        context,
        ConfirmReservation.of(
            booking_id=booking_id,
            reservation_id=reservation_id,
            expected_version=expected_version,
            reservation_version=reservation_version,
        ),
        idempotency_key=idempotency_key,
    )
