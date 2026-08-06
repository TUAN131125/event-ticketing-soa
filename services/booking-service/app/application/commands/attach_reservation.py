"""Atomic and idempotent AttachReservation command."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy.orm import Session

from app.application.commands.transition import BookingTransition, execute_transition
from app.config import Settings
from app.domain.entities import Booking
from app.domain.enums import BookingStatus, ReservationEvidenceStatus
from app.domain.exceptions import InvalidRequest, ReservationConflict
from app.domain.rules import (
    advisory_lock_id,
    validate_expected_version,
    validate_identifier,
)
from app.domain.value_objects import RequestContext
from app.infrastructure.database.repositories import (
    acquire_advisory_lock,
    get_booking_by_reservation,
)

RESERVATION_LOCK_SCOPE = "BookingReservation"


@dataclass(frozen=True, slots=True)
class AttachReservation(BookingTransition):
    scope: ClassVar[str] = "AttachReservation"

    target_booking_id: str
    reservation_id: str
    expected_version: int
    expires_at: datetime | None
    reservation_version: int | None
    confirmed: bool

    @classmethod
    def of(
        cls,
        *,
        booking_id: str,
        reservation_id: str,
        expected_version: int,
        expires_at: datetime | None = None,
        reservation_version: int | None = None,
        confirmed: bool = True,
    ) -> "AttachReservation":
        return cls(
            target_booking_id=validate_identifier(booking_id, "bookingId"),
            reservation_id=validate_identifier(reservation_id, "reservationId"),
            expected_version=validate_expected_version(expected_version),
            expires_at=expires_at,
            reservation_version=reservation_version,
            confirmed=confirmed,
        )

    @property
    def booking_id(self) -> str:
        return self.target_booking_id

    def request_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "bookingId": self.target_booking_id,
            "reservationId": self.reservation_id,
            "expectedVersion": self.expected_version,
        }
        if (
            self.expires_at is None
            and self.reservation_version is None
            and self.confirmed
        ):
            return payload
        payload.update(
            {
                "reservationExpiresAt": (
                    self.expires_at.isoformat() if self.expires_at else None
                ),
                "reservationVersion": self.reservation_version,
                "confirmed": self.confirmed,
            }
        )
        return payload

    def before_load(self, session: Session) -> None:
        """Serialize reservation ownership across legacy and canonical creates."""
        acquire_advisory_lock(
            session, advisory_lock_id(RESERVATION_LOCK_SCOPE, self.reservation_id)
        )
        owner = get_booking_by_reservation(
            session, self.reservation_id, for_update=True
        )
        if owner is not None and owner.booking_id != self.target_booking_id:
            raise ReservationConflict(self.reservation_id)

    def is_already_applied(self, booking: Booking) -> bool:
        if booking.reservation_id != self.reservation_id:
            if booking.reservation_id is None:
                return False
            raise InvalidRequest("Booking already has another reservation")

        accepted_statuses = (
            {
                ReservationEvidenceStatus.CONFIRMED,
                ReservationEvidenceStatus.RELEASE_PENDING,
                ReservationEvidenceStatus.RELEASED,
            }
            if self.confirmed
            else {
                ReservationEvidenceStatus.RESERVED,
                ReservationEvidenceStatus.CONFIRMED,
                ReservationEvidenceStatus.RELEASE_PENDING,
                ReservationEvidenceStatus.RELEASED,
            }
        )
        if booking.reservation_status not in accepted_statuses:
            return False
        if (
            self.expires_at is not None
            and booking.reservation_expires_at != self.expires_at
        ):
            raise InvalidRequest("Reservation expiry evidence does not match")
        if self.reservation_version is not None:
            current_version = booking.reservation_version
            if current_version is None or current_version < self.reservation_version:
                raise InvalidRequest("Reservation version evidence does not match")
        return True

    def apply(self, booking: Booking, now: datetime) -> None:
        booking.attach_reservation(
            reservation_id=self.reservation_id,
            expected_version=self.expected_version,
            now=now,
            expires_at=self.expires_at,
            reservation_version=self.reservation_version,
            confirmed=self.confirmed,
        )

    def audit_details(self, booking: Booking) -> dict[str, Any]:
        return {
            "reservationId": booking.reservation_id,
            "reservationStatus": booking.reservation_status.value,
            "reservationVersion": booking.reservation_version,
            "reservationExpiresAt": (
                booking.reservation_expires_at.isoformat()
                if booking.reservation_expires_at
                else None
            ),
        }


def attach_reservation(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    booking_id: str,
    reservation_id: str,
    expected_version: int,
    expires_at: datetime | None = None,
    reservation_version: int | None = None,
    confirmed: bool = True,
) -> Booking:
    return execute_transition(
        session,
        settings,
        context,
        AttachReservation.of(
            booking_id=booking_id,
            reservation_id=reservation_id,
            expected_version=expected_version,
            expires_at=expires_at,
            reservation_version=reservation_version,
            confirmed=confirmed,
        ),
        idempotency_key=idempotency_key,
    )
