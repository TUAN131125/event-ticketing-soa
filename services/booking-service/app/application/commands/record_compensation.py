"""Record an asynchronous compensation result and close the booking safely."""

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
from app.domain.enums import (
    BookingEventType,
    BookingStatus,
    CompensationStatus,
    PaymentStatus,
    ReservationEvidenceStatus,
)
from app.domain.rules import (
    validate_expected_version,
    validate_identifier,
    validate_reason,
)
from app.domain.value_objects import CompensationEvidence, RequestContext


@dataclass(frozen=True, slots=True)
class RecordCompensation(BookingTransition):
    scope: ClassVar[str] = "RecordCompensation"
    target_booking_id: str
    expected_version: int
    compensation_status: CompensationStatus
    evidence: CompensationEvidence
    reason: str | None

    @classmethod
    def of(
        cls,
        *,
        booking_id: str,
        expected_version: int,
        compensation_status: CompensationStatus,
        evidence: CompensationEvidence,
        reason: str | None,
    ) -> "RecordCompensation":
        return cls(
            target_booking_id=validate_identifier(booking_id, "bookingId"),
            expected_version=validate_expected_version(expected_version),
            compensation_status=compensation_status,
            evidence=evidence,
            reason=validate_reason(reason, "reason") if reason else None,
        )

    @property
    def booking_id(self) -> str:
        return self.target_booking_id

    def request_payload(self) -> dict[str, Any]:
        return {
            "bookingId": self.target_booking_id,
            "expectedVersion": self.expected_version,
            "compensationStatus": self.compensation_status.value,
            "reservationReleased": self.evidence.reservation_released,
            "paymentRefunded": self.evidence.payment_refunded,
            "providerReference": self.evidence.provider_reference,
            "resolvedPaymentStatus": (
                self.evidence.resolved_payment_status.value
                if self.evidence.resolved_payment_status is not None
                else None
            ),
            "reason": self.reason,
        }

    def is_already_applied(self, booking: Booking) -> bool:
        if booking.status in {BookingStatus.FAILED, BookingStatus.CANCELLED}:
            if self.compensation_status != CompensationStatus.COMPLETED:
                return False
            return self._evidence_is_recorded(booking)
        if booking.status != BookingStatus.COMPENSATION_PENDING:
            return False
        if booking.compensation_status != self.compensation_status:
            return False
        return self._evidence_is_recorded(booking)

    def _evidence_is_recorded(self, booking: Booking) -> bool:
        if (
            self.evidence.reservation_released
            and booking.reservation_status != ReservationEvidenceStatus.RELEASED
        ):
            return False
        if (
            self.evidence.payment_refunded
            and booking.payment_status != PaymentStatus.REFUNDED
        ):
            return False
        if (
            self.evidence.resolved_payment_status is not None
            and booking.payment_status != self.evidence.resolved_payment_status
        ):
            return False
        if (
            self.evidence.provider_reference is not None
            and booking.compensation_provider_reference
            != self.evidence.provider_reference
        ):
            return False
        if self.reason is not None and booking.compensation_reason != self.reason:
            return False
        return True

    def apply(self, booking: Booking, now: datetime) -> None:
        booking.record_compensation(
            expected_version=self.expected_version,
            compensation_status=self.compensation_status,
            evidence=self.evidence,
            reason=self.reason,
            now=now,
        )

    def audit_details(self, booking: Booking) -> dict[str, Any]:
        return {
            "compensationStatus": booking.compensation_status.value,
            "compensationAction": booking.compensation_action.value,
            "reservationStatus": booking.reservation_status.value,
            "paymentStatus": booking.payment_status.value,
        }

    def outbox_event(self, booking: Booking) -> OutboxEvent | None:
        if booking.status == BookingStatus.FAILED:
            return OutboxEvent(
                BookingEventType.FAILED,
                {
                    **event_payload(booking),
                    "failureCode": booking.failure_code,
                    "reason": booking.failure_reason,
                },
            )
        if booking.status == BookingStatus.CANCELLED:
            return OutboxEvent(
                BookingEventType.CANCELLED,
                {**event_payload(booking), "reason": booking.cancellation_reason},
            )
        return None


def record_compensation(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    booking_id: str,
    expected_version: int,
    compensation_status: CompensationStatus,
    evidence: CompensationEvidence,
    reason: str | None = None,
) -> Booking:
    return execute_transition(
        session,
        settings,
        context,
        RecordCompensation.of(
            booking_id=booking_id,
            expected_version=expected_version,
            compensation_status=compensation_status,
            evidence=evidence,
            reason=reason,
        ),
        idempotency_key=idempotency_key,
    )
