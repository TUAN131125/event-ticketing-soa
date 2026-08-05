"""Closed canonical Notification request schemas."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class EventEnvelopeRequest(ClosedModel):
    event_id: str = Field(alias="eventId", min_length=1, max_length=128)
    event_type: Literal[
        "booking.confirmed", "booking.failed", "event.changed", "ticket.issued"
    ] = Field(alias="eventType")
    schema_version: int = Field(alias="schemaVersion", ge=1)
    occurred_at: datetime = Field(alias="occurredAt")
    correlation_id: str = Field(alias="correlationId", min_length=1, max_length=128)
    aggregate_id: str = Field(alias="aggregateId", min_length=1, max_length=128)
    data: dict[str, Any]

    @field_validator("occurred_at")
    @classmethod
    def utc_only(cls, value: datetime) -> datetime:
        offset = value.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            raise ValueError("occurredAt must be UTC")
        return value


class TemplateUpdateRequest(ClosedModel):
    subject: str = Field(max_length=200)
    body: str = Field(max_length=10_000)
