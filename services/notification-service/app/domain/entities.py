"""Notification-owned delivery and template entities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.domain.enums import DeliveryStatus


@dataclass
class Delivery:
    id: str
    event_id: str
    channel: str
    status: DeliveryStatus
    attempt_count: int
    last_error_code: str | None
    to_address: str
    subject: str
    body: str
    created_at: datetime
    resource_version: int

    @classmethod
    def create(
        cls,
        delivery_id: str,
        event_id: str,
        to_address: str,
        subject: str,
        body: str,
    ) -> Delivery:
        return cls(
            id=delivery_id,
            event_id=event_id,
            channel="EMAIL",
            status=DeliveryStatus.PENDING,
            attempt_count=0,
            last_error_code=None,
            to_address=to_address,
            subject=subject,
            body=body,
            created_at=datetime.now(UTC),
            resource_version=1,
        )


@dataclass
class NotificationTemplate:
    code: str
    subject: str
    body: str
    resource_version: int
