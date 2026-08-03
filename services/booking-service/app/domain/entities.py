"""Persistence-independent booking aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.enums import BookingStatus, PaymentStatus
from app.domain.exceptions import InvalidRequest, VersionConflict
from app.domain.rules import (
    ensure_transition_allowed,
    validate_currency,
    validate_identifier,
    validate_items,
    validate_money,
    validate_reason,
)
from app.domain.value_objects import BookingItem


@dataclass(slots=True)
class Booking:
    booking_id: str
    customer_id: str
    event_id: str
    reservation_id: str
    payment_method: str
    items: tuple[BookingItem, ...]
    total_amount: Decimal
    currency: str
    status: BookingStatus
    payment_status: PaymentStatus
    resource_version: int
    created_at: datetime
    updated_at: datetime
    payment_id: str | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    cancellation_reason: str | None = None
    confirmed_at: datetime | None = None
    cancelled_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        booking_id: str,
        customer_id: str,
        event_id: str,
        reservation_id: str,
        payment_method: str,
        items: tuple[BookingItem, ...],
        total_amount: Decimal,
        currency: str,
        now: datetime,
    ) -> Booking:
        booking_id = validate_identifier(booking_id, "bookingId")
        customer_id = validate_identifier(customer_id, "customerId")
        event_id = validate_identifier(event_id, "eventId")
        reservation_id = validate_identifier(reservation_id, "reservationId")
        payment_method = validate_identifier(
            payment_method, "paymentMethod", max_length=40
        )
        currency = validate_currency(currency)
        amount = validate_money(total_amount, "totalAmount")
        normalized_items = validate_items(items, amount)
        return cls(
            booking_id=booking_id,
            customer_id=customer_id,
            event_id=event_id,
            reservation_id=reservation_id,
            payment_method=payment_method,
            items=normalized_items,
            total_amount=amount,
            currency=currency,
            status=BookingStatus.PENDING,
            payment_status=PaymentStatus.PENDING,
            resource_version=1,
            created_at=now,
            updated_at=now,
        )

    def _check_version(self, expected_version: int) -> None:
        if self.resource_version != expected_version:
            raise VersionConflict(expected_version, self.resource_version)

    def confirm(self, *, payment_id: str, expected_version: int, now: datetime) -> None:
        self._check_version(expected_version)
        ensure_transition_allowed(self.status, BookingStatus.CONFIRMED)
        self.payment_id = validate_identifier(payment_id, "paymentId")
        self.status = BookingStatus.CONFIRMED
        self.payment_status = PaymentStatus.SUCCEEDED
        self.confirmed_at = now
        self.updated_at = now
        self.resource_version += 1

    def fail(
        self,
        *,
        failure_code: str,
        reason: str,
        expected_version: int,
        now: datetime,
    ) -> None:
        self._check_version(expected_version)
        ensure_transition_allowed(self.status, BookingStatus.FAILED)
        self.failure_code = validate_identifier(failure_code, "failureCode")
        normalized_reason = validate_reason(reason)
        self.failure_reason = normalized_reason
        self.status = BookingStatus.FAILED
        self.payment_status = PaymentStatus.FAILED
        self.updated_at = now
        self.resource_version += 1

    def cancel(
        self,
        *,
        reason: str,
        expected_version: int,
        payment_status: PaymentStatus | None,
        now: datetime,
    ) -> None:
        self._check_version(expected_version)
        ensure_transition_allowed(self.status, BookingStatus.CANCELLED)
        normalized_reason = validate_reason(reason)
        if self.status == BookingStatus.CONFIRMED:
            if payment_status != PaymentStatus.REFUNDED:
                raise InvalidRequest(
                    "A confirmed booking can only be cancelled after payment "
                    "is refunded"
                )
            self.payment_status = PaymentStatus.REFUNDED
        elif payment_status is not None:
            if payment_status not in {PaymentStatus.FAILED, PaymentStatus.REFUNDED}:
                raise InvalidRequest("Invalid payment status for cancellation")
            self.payment_status = payment_status
        self.status = BookingStatus.CANCELLED
        self.cancellation_reason = normalized_reason
        self.cancelled_at = now
        self.updated_at = now
        self.resource_version += 1
