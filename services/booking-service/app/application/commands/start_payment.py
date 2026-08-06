"""Atomic and idempotent StartPayment command."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy.orm import Session

from app.application.commands.transition import BookingTransition, execute_transition
from app.config import Settings
from app.domain.entities import Booking
from app.domain.enums import PaymentStatus
from app.domain.exceptions import InvalidRequest
from app.domain.rules import validate_expected_version, validate_identifier
from app.domain.value_objects import RequestContext


@dataclass(frozen=True, slots=True)
class StartPayment(BookingTransition):
    scope: ClassVar[str] = "StartPayment"
    target_booking_id: str
    payment_id: str
    expected_version: int

    @classmethod
    def of(
        cls, *, booking_id: str, payment_id: str, expected_version: int
    ) -> "StartPayment":
        return cls(
            target_booking_id=validate_identifier(booking_id, "bookingId"),
            payment_id=validate_identifier(payment_id, "paymentId"),
            expected_version=validate_expected_version(expected_version),
        )

    @property
    def booking_id(self) -> str:
        return self.target_booking_id

    def request_payload(self) -> dict[str, Any]:
        return {
            "bookingId": self.target_booking_id,
            "paymentId": self.payment_id,
            "expectedVersion": self.expected_version,
        }

    def is_already_applied(self, booking: Booking) -> bool:
        if booking.payment_status == PaymentStatus.PENDING:
            return False
        if booking.payment_id != self.payment_id:
            raise InvalidRequest("Booking already has another payment started")
        return True

    def apply(self, booking: Booking, now: datetime) -> None:
        booking.start_payment(
            payment_id=self.payment_id,
            expected_version=self.expected_version,
            now=now,
        )

    def audit_details(self, booking: Booking) -> dict[str, Any]:
        return {
            "paymentId": booking.payment_id,
            "paymentStatus": booking.payment_status.value,
        }


def start_payment(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    booking_id: str,
    payment_id: str,
    expected_version: int,
) -> Booking:
    return execute_transition(
        session,
        settings,
        context,
        StartPayment.of(
            booking_id=booking_id,
            payment_id=payment_id,
            expected_version=expected_version,
        ),
        idempotency_key=idempotency_key,
    )
