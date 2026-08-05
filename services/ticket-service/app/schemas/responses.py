"""Canonical Ticket response schema."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import Ticket
from app.security.qr_tokens import create_qr_token


class TicketResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    ticket_id: str = Field(alias="ticketId")
    booking_id: str = Field(alias="bookingId")
    event_id: str = Field(alias="eventId")
    customer_id: str = Field(alias="customerId")
    seat_id: str = Field(alias="seatId")
    status: str
    qr_token: str | None = Field(default=None, alias="qrToken")
    resource_version: int = Field(alias="resourceVersion", ge=1)

    @classmethod
    def from_entity(cls, ticket: Ticket, signing_key: str) -> TicketResponse:
        status = "ISSUED" if ticket.status.value == "VALID" else ticket.status.value
        token = (
            create_qr_token(ticket.ticket_id, ticket.qr_version, signing_key)
            if ticket.status.value == "VALID"
            else None
        )
        return cls(
            ticketId=ticket.ticket_id,
            bookingId=ticket.booking_id,
            eventId=ticket.event_id,
            customerId=ticket.customer_id,
            seatId=ticket.seat_id,
            status=status,
            qrToken=token,
            resourceVersion=ticket.resource_version,
        )
