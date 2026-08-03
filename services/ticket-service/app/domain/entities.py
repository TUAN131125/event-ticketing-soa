"""Persistence-independent ticket aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import TicketStatus
from app.domain.exceptions import VersionConflict
from app.domain.rules import (
    ensure_transition_allowed,
    validate_expected_version,
    validate_identifier,
    validate_reason,
)


@dataclass(slots=True)
class Ticket:
    ticket_id: str
    booking_id: str
    customer_id: str
    event_id: str
    payment_id: str
    seat_id: str
    seat_label: str
    ticket_type: str
    status: TicketStatus
    qr_version: int
    resource_version: int
    issued_at: datetime
    updated_at: datetime
    checked_in_at: datetime | None = None
    checked_in_gate_id: str | None = None
    checked_in_by: str | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None

    @classmethod
    def issue(
        cls,
        *,
        ticket_id: str,
        booking_id: str,
        customer_id: str,
        event_id: str,
        payment_id: str,
        seat_id: str,
        seat_label: str,
        ticket_type: str,
        now: datetime,
    ) -> Ticket:
        return cls(
            ticket_id=validate_identifier(ticket_id, "ticketId"),
            booking_id=validate_identifier(booking_id, "bookingId"),
            customer_id=validate_identifier(customer_id, "customerId"),
            event_id=validate_identifier(event_id, "eventId"),
            payment_id=validate_identifier(payment_id, "paymentId"),
            seat_id=validate_identifier(seat_id, "seatId"),
            seat_label=validate_identifier(seat_label, "seatLabel"),
            ticket_type=validate_identifier(ticket_type, "ticketType"),
            status=TicketStatus.VALID,
            qr_version=1,
            resource_version=1,
            issued_at=now,
            updated_at=now,
        )

    def check_version(self, expected_version: int) -> None:
        expected = validate_expected_version(expected_version)
        if self.resource_version != expected:
            raise VersionConflict(expected, self.resource_version)

    def check_in(
        self,
        *,
        gate_id: str,
        checked_in_by: str,
        expected_version: int,
        now: datetime,
    ) -> None:
        self.check_version(expected_version)
        ensure_transition_allowed(self.status, TicketStatus.CHECKED_IN)
        self.checked_in_gate_id = validate_identifier(gate_id, "gateId")
        self.checked_in_by = validate_identifier(checked_in_by, "checkedInBy")
        self.checked_in_at = now
        self.status = TicketStatus.CHECKED_IN
        self._advance(now)

    def cancel(self, *, reason: str, expected_version: int, now: datetime) -> None:
        self.check_version(expected_version)
        ensure_transition_allowed(self.status, TicketStatus.CANCELLED)
        self.cancellation_reason = validate_reason(reason)
        self.cancelled_at = now
        self.status = TicketStatus.CANCELLED
        self._advance(now)

    def regenerate_qr(self, *, expected_version: int, now: datetime) -> None:
        self.check_version(expected_version)
        ensure_transition_allowed(self.status, TicketStatus.VALID)
        self.qr_version += 1
        self._advance(now)

    def _advance(self, now: datetime) -> None:
        self.resource_version += 1
        self.updated_at = now
