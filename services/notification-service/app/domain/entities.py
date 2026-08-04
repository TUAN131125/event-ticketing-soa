"""Entity thuan nghiep vu cua Notification Service - khong phu thuoc
FastAPI/DB/provider that su. Khop voi 4 bang so huu trong SQL baseline
Giai doan 5: inbound_events, deliveries, delivery_attempts, templates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.domain.enums import Channel, DeliveryStatus, EventType


@dataclass
class InboundEvent:
    """1 dong / 1 eventId da nhan - la hang rao idempotency chinh (NOT-01,
    NOT-02, NOT-03): eventId la PRIMARY KEY nen chi xu ly duoc 1 lan."""

    event_id: str
    event_type: EventType
    schema_version: int
    correlation_id: str
    aggregate_id: str
    payload: dict[str, Any]
    received_at: datetime

    @classmethod
    def create(
        cls,
        event_id: str,
        event_type: EventType,
        schema_version: int,
        correlation_id: str,
        aggregate_id: str,
        payload: dict[str, Any],
    ) -> "InboundEvent":
        return cls(
            event_id=event_id,
            event_type=event_type,
            schema_version=schema_version,
            correlation_id=correlation_id,
            aggregate_id=aggregate_id,
            payload=payload,
            received_at=datetime.now(timezone.utc),
        )


@dataclass
class Delivery:
    id: str
    event_id: str
    channel: Channel
    destination_hash: str
    status: DeliveryStatus
    attempt_count: int
    next_attempt_at: Optional[datetime]
    last_error_code: Optional[str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, delivery_id: str, event_id: str, channel: Channel, destination_hash: str) -> "Delivery":
        now = datetime.now(timezone.utc)
        return cls(
            id=delivery_id,
            event_id=event_id,
            channel=channel,
            destination_hash=destination_hash,
            status=DeliveryStatus.PENDING,
            attempt_count=0,
            next_attempt_at=None,
            last_error_code=None,
            created_at=now,
            updated_at=now,
        )

    def mark_sending(self) -> None:
        self.status = DeliveryStatus.SENDING
        self.updated_at = datetime.now(timezone.utc)

    def mark_delivered(self) -> None:
        self.status = DeliveryStatus.DELIVERED
        self.attempt_count += 1
        self.next_attempt_at = None
        self.last_error_code = None
        self.updated_at = datetime.now(timezone.utc)

    def mark_failed(self, error_code: str, *, max_attempts: int, backoff_seconds: int) -> None:
        """Sau khi 1 attempt that bai: neu con duoi nguong max_attempts thi
        chuyen RETRY_PENDING kem next_attempt_at (exponential backoff);
        vuot nguong thi chuyen DEAD_LETTER (NOT-06)."""
        from datetime import timedelta

        self.attempt_count += 1
        self.last_error_code = error_code
        if self.attempt_count >= max_attempts:
            self.status = DeliveryStatus.DEAD_LETTER
            self.next_attempt_at = None
        else:
            self.status = DeliveryStatus.RETRY_PENDING
            delay = backoff_seconds * (2 ** (self.attempt_count - 1))
            self.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        self.updated_at = datetime.now(timezone.utc)


@dataclass
class DeliveryAttempt:
    delivery_id: str
    attempt_no: int
    status: DeliveryStatus
    error_code: Optional[str]
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Template:
    code: str
    subject: str
    body: str
    resource_version: int
    updated_at: datetime

    @classmethod
    def create(cls, code: str, subject: str, body: str) -> "Template":
        return cls(
            code=code, subject=subject, body=body, resource_version=1,
            updated_at=datetime.now(timezone.utc),
        )

    def replace(self, subject: str, body: str) -> None:
        self.subject = subject
        self.body = body
        self.resource_version += 1
        self.updated_at = datetime.now(timezone.utc)
