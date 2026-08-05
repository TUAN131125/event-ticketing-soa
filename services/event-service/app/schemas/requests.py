"""Request schema cua Event Service."""

from pydantic import BaseModel


class TicketTypeRequest(BaseModel):
    type: str
    price: int


class EventCreateRequest(BaseModel):
    name: str
    location: str
    startTime: str
    ticketTypes: list[TicketTypeRequest] = []


class EventUpdateRequest(BaseModel):
    name: str | None = None
    location: str | None = None
    startTime: str | None = None
