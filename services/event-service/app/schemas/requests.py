"""Request schema cua Event Service."""
from typing import Optional

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
    name: Optional[str] = None
    location: Optional[str] = None
    startTime: Optional[str] = None
