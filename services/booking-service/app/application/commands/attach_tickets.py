"""Atomic and idempotent AttachTickets command."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy.orm import Session

from app.application.commands.transition import BookingTransition, execute_transition
from app.config import Settings
from app.domain.entities import Booking
from app.domain.exceptions import InvalidRequest
from app.domain.rules import (
    validate_expected_version,
    validate_identifier,
    validate_ticket_ids,
)
from app.domain.value_objects import RequestContext


@dataclass(frozen=True, slots=True)
class AttachTickets(BookingTransition):
    scope: ClassVar[str] = "AttachTickets"
    target_booking_id: str
    ticket_ids: tuple[str, ...]
    expected_version: int

    @classmethod
    def of(
        cls,
        *,
        booking_id: str,
        ticket_ids: tuple[str, ...],
        expected_version: int,
    ) -> "AttachTickets":
        return cls(
            target_booking_id=validate_identifier(booking_id, "bookingId"),
            ticket_ids=validate_ticket_ids(ticket_ids),
            expected_version=validate_expected_version(expected_version),
        )

    @property
    def booking_id(self) -> str:
        return self.target_booking_id

    def request_payload(self) -> dict[str, Any]:
        return {
            "bookingId": self.target_booking_id,
            "ticketIds": list(self.ticket_ids),
            "expectedVersion": self.expected_version,
        }

    def is_already_applied(self, booking: Booking) -> bool:
        if not booking.ticket_ids:
            return False
        if booking.ticket_ids != self.ticket_ids:
            raise InvalidRequest("Booking already records another ticket set")
        return True

    def apply(self, booking: Booking, now: datetime) -> None:
        booking.attach_tickets(
            ticket_ids=self.ticket_ids,
            expected_version=self.expected_version,
            now=now,
        )

    def audit_details(self, booking: Booking) -> dict[str, Any]:
        return {"ticketIds": list(booking.ticket_ids)}


def attach_tickets(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    booking_id: str,
    ticket_ids: tuple[str, ...],
    expected_version: int,
) -> Booking:
    return execute_transition(
        session,
        settings,
        context,
        AttachTickets.of(
            booking_id=booking_id,
            ticket_ids=ticket_ids,
            expected_version=expected_version,
        ),
        idempotency_key=idempotency_key,
    )
