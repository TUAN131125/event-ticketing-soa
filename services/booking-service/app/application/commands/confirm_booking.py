"""Atomic and idempotent ConfirmBooking command."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy.orm import Session

from app.application.commands.transition import (
    BookingTransition,
    OutboxEvent,
    execute_transition,
)
from app.application.common import event_payload
from app.config import Settings
from app.domain.entities import Booking
from app.domain.enums import BookingEventType, BookingStatus, PaymentStatus
from app.domain.exceptions import InvalidRequest
from app.domain.rules import (
    validate_expected_version,
    validate_identifier,
    validate_ticket_ids,
)
from app.domain.value_objects import RequestContext


@dataclass(frozen=True, slots=True)
class ConfirmBooking(BookingTransition):
    scope: ClassVar[str] = "ConfirmBooking"
    target_booking_id: str
    expected_version: int
    reservation_id: str | None = None
    payment_id: str | None = None
    payment_status: PaymentStatus | None = None
    ticket_ids: tuple[str, ...] | None = None
    seat_confirmed: bool | None = None
    payment_captured: bool | None = None
    tickets_issued: bool | None = None

    @classmethod
    def of(
        cls,
        *,
        booking_id: str,
        expected_version: int,
        reservation_id: str | None = None,
        payment_id: str | None = None,
        payment_status: PaymentStatus | None = None,
        ticket_ids: tuple[str, ...] | None = None,
        seat_confirmed: bool | None = None,
        payment_captured: bool | None = None,
        tickets_issued: bool | None = None,
    ) -> ConfirmBooking:
        return cls(
            target_booking_id=validate_identifier(booking_id, "bookingId"),
            expected_version=validate_expected_version(expected_version),
            reservation_id=(
                validate_identifier(reservation_id, "reservationId")
                if reservation_id is not None
                else None
            ),
            payment_id=(
                validate_identifier(payment_id, "paymentId")
                if payment_id is not None
                else None
            ),
            payment_status=payment_status,
            ticket_ids=(
                validate_ticket_ids(ticket_ids) if ticket_ids is not None else None
            ),
            seat_confirmed=seat_confirmed,
            payment_captured=payment_captured,
            tickets_issued=tickets_issued,
        )

    @property
    def booking_id(self) -> str:
        return self.target_booking_id

    def request_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "bookingId": self.target_booking_id,
            "expectedVersion": self.expected_version,
        }
        optional = {
            "reservationId": self.reservation_id,
            "paymentId": self.payment_id,
            "paymentStatus": (
                self.payment_status.value if self.payment_status is not None else None
            ),
            "ticketIds": list(self.ticket_ids) if self.ticket_ids is not None else None,
            "seatConfirmed": self.seat_confirmed,
            "paymentCaptured": self.payment_captured,
            "ticketsIssued": self.tickets_issued,
        }
        if any(value is not None for value in optional.values()):
            payload.update(optional)
        return payload

    def is_already_applied(self, booking: Booking) -> bool:
        if booking.status != BookingStatus.CONFIRMED:
            return False
        self._validate_evidence(booking)
        return True

    def apply(self, booking: Booking, now: datetime) -> None:
        self._validate_evidence(booking)
        booking.confirm(expected_version=self.expected_version, now=now)

    def audit_details(self, booking: Booking) -> dict[str, Any]:
        return {
            "reservationStatus": booking.reservation_status.value,
            "paymentStatus": booking.payment_status.value,
            "ticketIds": list(booking.ticket_ids),
        }

    def outbox_event(self, booking: Booking) -> OutboxEvent:
        return OutboxEvent(BookingEventType.CONFIRMED, event_payload(booking))

    def _validate_evidence(self, booking: Booking) -> None:
        if (
            self.reservation_id is not None
            and self.reservation_id != booking.reservation_id
        ):
            raise InvalidRequest("reservationId does not match booking evidence")
        if self.payment_id is not None and self.payment_id != booking.payment_id:
            raise InvalidRequest("paymentId does not match booking evidence")
        if (
            self.payment_status is not None
            and self.payment_status != booking.payment_status
        ):
            raise InvalidRequest("paymentStatus does not match booking evidence")
        if self.ticket_ids is not None and self.ticket_ids != booking.ticket_ids:
            raise InvalidRequest("ticketIds do not match booking evidence")
        if self.seat_confirmed is False:
            raise InvalidRequest("seatConfirmed must be true")
        if self.payment_captured is False:
            raise InvalidRequest("paymentCaptured must be true")
        if self.tickets_issued is False:
            raise InvalidRequest("ticketsIssued must be true")


def confirm_booking(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    booking_id: str,
    expected_version: int,
    reservation_id: str | None = None,
    payment_id: str | None = None,
    payment_status: PaymentStatus | None = None,
    ticket_ids: tuple[str, ...] | None = None,
    seat_confirmed: bool | None = None,
    payment_captured: bool | None = None,
    tickets_issued: bool | None = None,
) -> Booking:
    return execute_transition(
        session,
        settings,
        context,
        ConfirmBooking.of(
            booking_id=booking_id,
            expected_version=expected_version,
            reservation_id=reservation_id,
            payment_id=payment_id,
            payment_status=payment_status,
            ticket_ids=ticket_ids,
            seat_confirmed=seat_confirmed,
            payment_captured=payment_captured,
            tickets_issued=tickets_issued,
        ),
        idempotency_key=idempotency_key,
    )
