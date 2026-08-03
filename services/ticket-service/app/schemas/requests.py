"""Closed request contracts for ticket commands."""

from pydantic import BaseModel, ConfigDict, Field


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TicketDefinitionRequest(ClosedModel):
    seat_id: str = Field(alias="seatId", min_length=1, max_length=128)
    seat_label: str | None = Field(
        default=None, alias="seatLabel", min_length=1, max_length=128
    )
    ticket_type: str = Field(alias="ticketType", min_length=1, max_length=128)


class IssueTicketsRequest(ClosedModel):
    booking_id: str = Field(alias="bookingId", min_length=1, max_length=128)
    customer_id: str = Field(alias="customerId", min_length=1, max_length=128)
    event_id: str = Field(alias="eventId", min_length=1, max_length=128)
    payment_id: str = Field(alias="paymentId", min_length=1, max_length=128)
    tickets: list[TicketDefinitionRequest] = Field(min_length=1, max_length=50)


class CancelTicketRequest(ClosedModel):
    reason: str = Field(min_length=1, max_length=2_000)
    expected_version: int = Field(alias="expectedVersion", ge=1)


class CheckInTicketRequest(ClosedModel):
    qr_token: str = Field(alias="qrToken", min_length=1, max_length=256)
    gate_id: str = Field(alias="gateId", min_length=1, max_length=128)
    expected_version: int = Field(alias="expectedVersion", ge=1)


class RegenerateQrRequest(ClosedModel):
    expected_version: int = Field(alias="expectedVersion", ge=1)
