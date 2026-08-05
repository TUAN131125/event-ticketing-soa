"""Canonical Notification response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import Delivery


class DeliveryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    delivery_id: str = Field(alias="deliveryId")
    event_id: str = Field(alias="eventId")
    channel: str
    status: str
    attempt_count: int = Field(alias="attemptCount", ge=0)
    last_error_code: str | None = Field(default=None, alias="lastErrorCode")
    created_at: datetime = Field(alias="createdAt")

    @classmethod
    def from_entity(cls, delivery: Delivery) -> DeliveryResponse:
        return cls(
            deliveryId=delivery.id,
            eventId=delivery.event_id,
            channel=delivery.channel,
            status=delivery.status.value,
            attemptCount=delivery.attempt_count,
            lastErrorCode=delivery.last_error_code,
            createdAt=delivery.created_at,
        )
