"""Pydantic response schema - khop CHINH XAC hop dong (Giai doan 5)."""
from __future__ import annotations

from pydantic import BaseModel

from app.domain.entities import Delivery, Template


class DeliveryResponse(BaseModel):
    deliveryId: str
    eventId: str
    channel: str
    status: str
    attemptCount: int
    lastErrorCode: str | None
    createdAt: str

    @classmethod
    def from_entity(cls, delivery: Delivery) -> "DeliveryResponse":
        return cls(
            deliveryId=delivery.id,
            eventId=delivery.event_id,
            channel=delivery.channel.value,
            status=delivery.status.value,
            attemptCount=delivery.attempt_count,
            lastErrorCode=delivery.last_error_code,
            createdAt=delivery.created_at.isoformat(),
        )


class TemplateResponse(BaseModel):
    templateCode: str
    subject: str
    resourceVersion: int
    updatedAt: str

    @classmethod
    def from_entity(cls, template: Template) -> "TemplateResponse":
        return cls(
            templateCode=template.code,
            subject=template.subject,
            resourceVersion=template.resource_version,
            updatedAt=template.updated_at.isoformat(),
        )
