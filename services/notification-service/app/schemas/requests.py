"""Pydantic request schema - tang bien doi du lieu vao/ra HTTP.

Ten truong giu camelCase (correlationId, bookingId, ...) de khop dung hop
dong payload ma ESB gui toi (xem contracts/event-messages.schema.json), khong doi sang
snake_case noi bo.
"""
from pydantic import BaseModel


class BookingConfirmedPayload(BaseModel):
    event: str
    correlationId: str
    bookingId: str
    customerEmail: str
    ticketIds: list[str] = []


class BookingFailedPayload(BaseModel):
    event: str
    correlationId: str
    bookingId: str
    customerEmail: str = ""
    reason: str = ""
