"""Pydantic response schema."""
from __future__ import annotations

from pydantic import BaseModel

from app.domain.entities import Delivery


class WebhookResultResponse(BaseModel):
    status: str


class DeliveryResponse(BaseModel):
    id: str
    type: str
    correlationId: str
    toEmail: str
    subject: str
    status: str
    createdAt: str

    @classmethod
    def from_entity(cls, delivery: Delivery) -> DeliveryResponse:
        return cls(
            id=delivery.id,
            type=delivery.type.value,
            correlationId=delivery.correlation_id,
            toEmail=delivery.to_email,
            subject=delivery.subject,
            status=delivery.status.value,
            createdAt=delivery.created_at.isoformat(),
        )
