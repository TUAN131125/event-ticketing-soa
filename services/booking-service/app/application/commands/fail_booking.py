"""Atomic and idempotent FailBooking command with compensation evidence."""

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
from app.domain.enums import BookingEventType, BookingStatus, CompensationStatus
from app.domain.exceptions import InvalidRequest
from app.domain.rules import (
    validate_expected_version,
    validate_identifier,
    validate_reason,
)
from app.domain.value_objects import CompensationEvidence, RequestContext


@dataclass(frozen=True, slots=True)
class FailBooking(BookingTransition):
    scope: ClassVar[str] = "FailBooking"
    target_booking_id: str
    failure_code: str
    reason: str
    expected_version: int
    compensation_status: CompensationStatus | None
    evidence: CompensationEvidence

    @classmethod
    def of(
        cls,
        *,
        booking_id: str,
        failure_code: str,
        reason: str,
        expected_version: int,
        compensation_status: CompensationStatus | None = None,
        evidence: CompensationEvidence | None = None,
    ) -> "FailBooking":
        return cls(
            target_booking_id=validate_identifier(booking_id, "bookingId"),
            failure_code=validate_identifier(failure_code, "failureCode"),
            reason=validate_reason(reason),
            expected_version=validate_expected_version(expected_version),
            compensation_status=compensation_status,
            evidence=evidence or CompensationEvidence(),
        )

    @property
    def booking_id(self) -> str:
        return self.target_booking_id

    def request_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "bookingId": self.target_booking_id,
            "failureCode": self.failure_code,
            "reason": self.reason,
            "expectedVersion": self.expected_version,
        }
        if self.compensation_status is None and self.evidence == CompensationEvidence():
            return payload
        payload.update(
            {
                "compensationStatus": (
                    self.compensation_status.value
                    if self.compensation_status is not None
                    else None
                ),
                "reservationReleased": self.evidence.reservation_released,
                "paymentRefunded": self.evidence.payment_refunded,
                "providerReference": self.evidence.provider_reference,
                "resolvedPaymentStatus": (
                    self.evidence.resolved_payment_status.value
                    if self.evidence.resolved_payment_status is not None
                    else None
                ),
            }
        )
        return payload

    def is_already_applied(self, booking: Booking) -> bool:
        if booking.status not in {
            BookingStatus.FAILED,
            BookingStatus.COMPENSATION_PENDING,
        }:
            return False
        if (
            booking.failure_code != self.failure_code
            or booking.failure_reason != self.reason
        ):
            raise InvalidRequest("Booking already records another failure reason")
        expected = self.compensation_status
        if expected is not None and booking.compensation_status != expected:
            return False
        return True

    def apply(self, booking: Booking, now: datetime) -> None:
        booking.fail(
            failure_code=self.failure_code,
            reason=self.reason,
            expected_version=self.expected_version,
            compensation_status=self.compensation_status,
            evidence=self.evidence,
            now=now,
        )

    def audit_details(self, booking: Booking) -> dict[str, Any]:
        return {
            "failureCode": booking.failure_code,
            "paymentStatus": booking.payment_status.value,
            "reservationStatus": booking.reservation_status.value,
            "compensationStatus": booking.compensation_status.value,
            "compensationAction": booking.compensation_action.value,
            "intendedTerminalStatus": (
                booking.intended_terminal_status.value
                if booking.intended_terminal_status
                else None
            ),
        }

    def outbox_event(self, booking: Booking) -> OutboxEvent | None:
        if booking.status != BookingStatus.FAILED:
            return None
        return OutboxEvent(
            BookingEventType.FAILED,
            {
                **event_payload(booking),
                "failureCode": booking.failure_code,
                "reason": booking.failure_reason,
            },
        )


def fail_booking(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    booking_id: str,
    failure_code: str,
    reason: str,
    expected_version: int,
    compensation_status: CompensationStatus | None = None,
    evidence: CompensationEvidence | None = None,
) -> Booking:
    return execute_transition(
        session,
        settings,
        context,
        FailBooking.of(
            booking_id=booking_id,
            failure_code=failure_code,
            reason=reason,
            expected_version=expected_version,
            compensation_status=compensation_status,
            evidence=evidence or CompensationEvidence(),
        ),
        idempotency_key=idempotency_key,
    )
