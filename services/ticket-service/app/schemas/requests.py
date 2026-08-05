"""Closed canonical Ticket request schemas."""

from pydantic import BaseModel, ConfigDict, Field


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TicketDefinitionRequest(ClosedModel):
    seat_id: str = Field(alias="seatId", min_length=1, max_length=128)


class IssueTicketsRequest(ClosedModel):
    booking_id: str = Field(alias="bookingId", min_length=1, max_length=128)
    event_id: str = Field(alias="eventId", min_length=1, max_length=128)
    customer_id: str = Field(alias="customerId", min_length=1, max_length=128)
    items: list[TicketDefinitionRequest] = Field(min_length=1, max_length=50)


class ValidateTicketRequest(ClosedModel):
    qr_token: str = Field(alias="qrToken", min_length=16, max_length=256)
