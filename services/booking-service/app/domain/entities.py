"""Persistence-independent canonical Booking aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.domain.enums import BookingStatus, PaymentStatus
from app.domain.exceptions import InvalidRequest, VersionConflict
from app.domain.rules import validate_currency, validate_identifier, validate_items
from app.domain.value_objects import BookingItem


@dataclass(slots=True)
class Booking:
    booking_id: str
    customer_id: str
    event_id: str
    items: tuple[BookingItem, ...]
    total_amount: Decimal
    currency: str
    status: BookingStatus
    resource_version: int
    created_at: datetime
    updated_at: datetime
    reservation_id: str | None = None
    payment_id: str | None = None
    payment_status: PaymentStatus = PaymentStatus.PENDING
    ticket_ids: tuple[str, ...] = ()
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
        items: tuple[BookingItem, ...],
        currency: str,
        now: datetime,
    ) -> Booking:
        normalized = validate_items(
            items, sum((item.unit_price for item in items), Decimal(0))
        )
        return cls(
            booking_id=validate_identifier(booking_id, "bookingId"),
            customer_id=validate_identifier(customer_id, "customerId"),
            event_id=validate_identifier(event_id, "eventId"),
            items=normalized,
            total_amount=sum((item.unit_price for item in normalized), Decimal(0)),
            currency=validate_currency(currency),
            status=BookingStatus.PENDING,
            resource_version=1,
            created_at=now,
            updated_at=now,
        )

    def transition(
        self,
        operation: str,
        payload: dict[str, Any],
        *,
        expected_version: int,
        now: datetime,
    ) -> None:
        if self.resource_version != expected_version:
            raise VersionConflict(expected_version, self.resource_version)
        handlers = {
            "bookingReservation": self._reservation,
            "bookingPaymentStarted": self._payment_started,
            "bookingPaymentResult": self._payment_result,
            "bookingTickets": self._tickets,
            "bookingConfirm": self._confirm,
            "bookingFail": self._fail,
            "bookingCancel": self._cancel,
        }
        try:
            handlers[operation](payload, now)
        except KeyError as exc:
            raise InvalidRequest("Unsupported booking transition") from exc
        self.resource_version += 1
        self.updated_at = now

    def _reservation(self, payload: dict[str, Any], _now: datetime) -> None:
        if self.status != BookingStatus.PENDING:
            raise InvalidRequest(
                "Reservation can only be attached to a pending booking"
            )
        self.reservation_id = validate_identifier(
            str(payload["reservationId"]), "reservationId"
        )
        self.status = BookingStatus.SEAT_RESERVED

    def _payment_started(self, payload: dict[str, Any], _now: datetime) -> None:
        if self.status != BookingStatus.SEAT_RESERVED:
            raise InvalidRequest("Payment can only start after seats are reserved")
        self.payment_id = validate_identifier(str(payload["paymentId"]), "paymentId")
        self.status = BookingStatus.PAYMENT_PROCESSING

    def _payment_result(self, payload: dict[str, Any], _now: datetime) -> None:
        if self.status != BookingStatus.PAYMENT_PROCESSING:
            raise InvalidRequest("Payment result requires payment processing state")
        self.payment_id = validate_identifier(str(payload["paymentId"]), "paymentId")
        self.payment_status = PaymentStatus(str(payload["paymentStatus"]))

    def _tickets(self, payload: dict[str, Any], _now: datetime) -> None:
        if self.payment_status != PaymentStatus.CAPTURED:
            raise InvalidRequest("Tickets require a captured payment")
        self.ticket_ids = tuple(
            validate_identifier(str(value), "ticketId")
            for value in payload["ticketIds"]
        )

    def _confirm(self, payload: dict[str, Any], now: datetime) -> None:
        if (
            self.status != BookingStatus.PAYMENT_PROCESSING
            or self.payment_status != PaymentStatus.CAPTURED
            or not self.reservation_id
            or not self.ticket_ids
        ):
            raise InvalidRequest("Booking confirmation evidence is incomplete")
        if str(payload["reservationId"]) != self.reservation_id:
            raise InvalidRequest("Reservation evidence does not match")
        if str(payload["paymentId"]) != self.payment_id:
            raise InvalidRequest("Payment evidence does not match")
        if tuple(payload["ticketIds"]) != self.ticket_ids:
            raise InvalidRequest("Ticket evidence does not match")
        self.status = BookingStatus.CONFIRMED
        self.confirmed_at = now

    def _fail(self, payload: dict[str, Any], _now: datetime) -> None:
        self.failure_code = validate_identifier(
            str(payload["reasonCode"]), "reasonCode"
        )
        self.status = (
            BookingStatus.COMPENSATION_PENDING
            if payload["compensationStatus"] == "PENDING"
            else BookingStatus.FAILED
        )

    def _cancel(self, payload: dict[str, Any], now: datetime) -> None:
        self.cancellation_reason = validate_identifier(
            str(payload["reasonCode"]), "reasonCode"
        )
        self.status = (
            BookingStatus.COMPENSATION_PENDING
            if payload["compensationStatus"] == "PENDING"
            else BookingStatus.CANCELLED
        )
        if self.status == BookingStatus.CANCELLED:
            self.cancelled_at = now
