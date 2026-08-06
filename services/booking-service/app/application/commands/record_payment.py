"""Atomic and idempotent RecordPayment command."""

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
class RecordPayment(BookingTransition):
    scope: ClassVar[str] = "RecordPayment"
    target_booking_id: str
    payment_id: str
    payment_status: PaymentStatus
    expected_version: int
    provider_reference: str | None = None
    failure_code: str | None = None
    legacy_succeeded: bool | None = None

    @classmethod
    def of(
        cls,
        *,
        booking_id: str,
        payment_id: str,
        expected_version: int,
        payment_status: PaymentStatus | None = None,
        succeeded: bool | None = None,
        provider_reference: str | None = None,
        failure_code: str | None = None,
    ) -> RecordPayment:
        normalized_status = cls._resolve_status(payment_status, succeeded)
        return cls(
            target_booking_id=validate_identifier(booking_id, "bookingId"),
            payment_id=validate_identifier(payment_id, "paymentId"),
            payment_status=normalized_status,
            expected_version=validate_expected_version(expected_version),
            provider_reference=(
                validate_identifier(provider_reference, "providerReference")
                if provider_reference is not None
                else None
            ),
            failure_code=(
                validate_identifier(failure_code, "failureCode")
                if failure_code is not None
                else None
            ),
            legacy_succeeded=succeeded if payment_status is None else None,
        )

    @property
    def booking_id(self) -> str:
        return self.target_booking_id

    def request_payload(self) -> dict[str, Any]:
        if self.legacy_succeeded is not None:
            return {
                "bookingId": self.target_booking_id,
                "paymentId": self.payment_id,
                "succeeded": self.legacy_succeeded,
                "expectedVersion": self.expected_version,
            }
        return {
            "bookingId": self.target_booking_id,
            "paymentId": self.payment_id,
            "paymentStatus": self.payment_status.value,
            "expectedVersion": self.expected_version,
            "providerReference": self.provider_reference,
            "failureCode": self.failure_code,
        }

    def is_already_applied(self, booking: Booking) -> bool:
        if booking.payment_status in {PaymentStatus.PROCESSING, PaymentStatus.PENDING}:
            return False
        if booking.payment_id != self.payment_id:
            raise InvalidRequest("Booking already records another payment")
        if booking.payment_status != self.payment_status:
            # UNKNOWN can be reconciled to a final result using a new command.
            return False
        if (
            self.provider_reference is not None
            and booking.payment_provider_reference != self.provider_reference
        ):
            raise InvalidRequest("Payment provider evidence does not match")
        if (
            self.failure_code is not None
            and booking.payment_failure_code != self.failure_code
        ):
            raise InvalidRequest("Payment failure evidence does not match")
        return True

    def apply(self, booking: Booking, now: datetime) -> None:
        booking.record_payment(
            payment_id=self.payment_id,
            payment_status=self.payment_status,
            expected_version=self.expected_version,
            provider_reference=self.provider_reference,
            failure_code=self.failure_code,
            now=now,
        )

    def audit_details(self, booking: Booking) -> dict[str, Any]:
        return {
            "paymentId": booking.payment_id,
            "paymentStatus": booking.payment_status.value,
            "providerReference": booking.payment_provider_reference,
            "failureCode": booking.payment_failure_code,
            "compensationAction": booking.compensation_action.value,
        }

    @staticmethod
    def _resolve_status(
        payment_status: PaymentStatus | None, succeeded: bool | None
    ) -> PaymentStatus:
        if payment_status is None and succeeded is None:
            raise InvalidRequest("paymentStatus or succeeded is required")
        legacy = (
            PaymentStatus.SUCCEEDED
            if succeeded is True
            else PaymentStatus.FAILED
            if succeeded is False
            else None
        )
        if (
            payment_status is not None
            and legacy is not None
            and payment_status != legacy
        ):
            raise InvalidRequest("paymentStatus and succeeded disagree")
        resolved = payment_status or legacy
        if resolved is None:
            raise InvalidRequest("paymentStatus or succeeded is required")
        return resolved


def record_payment(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    booking_id: str,
    payment_id: str,
    expected_version: int,
    payment_status: PaymentStatus | None = None,
    succeeded: bool | None = None,
    provider_reference: str | None = None,
    failure_code: str | None = None,
) -> Booking:
    return execute_transition(
        session,
        settings,
        context,
        RecordPayment.of(
            booking_id=booking_id,
            payment_id=payment_id,
            payment_status=payment_status,
            succeeded=succeeded,
            expected_version=expected_version,
            provider_reference=provider_reference,
            failure_code=failure_code,
        ),
        idempotency_key=idempotency_key,
    )
