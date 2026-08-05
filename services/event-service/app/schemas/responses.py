"""Response schema cua Event Service."""

from __future__ import annotations

from pydantic import BaseModel

from app.domain.entities import Event


class TicketTypeResponse(BaseModel):
    type: str
    price: int


class EventResponse(BaseModel):
    id: str
    name: str
    location: str
    startTime: str
    status: str
    ticketTypes: list[TicketTypeResponse]

    @classmethod
    def from_entity(cls, event: Event) -> EventResponse:
        return cls(
            id=event.id,
            name=event.name,
            location=event.location,
            startTime=event.start_time,
            status=event.status.value,
            ticketTypes=[
                TicketTypeResponse(type=t.type, price=t.price)
                for t in event.ticket_types
            ],
        )
