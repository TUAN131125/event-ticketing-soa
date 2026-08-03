"""Broker-neutral serialization of a persisted outbox row."""

from typing import Any

from app.infrastructure.database.models import OutboxEventModel


def outbox_event_envelope(event: OutboxEventModel) -> dict[str, Any]:
    return {
        "eventId": event.event_id,
        "eventType": event.event_type,
        "aggregateType": event.aggregate_type,
        "aggregateId": event.aggregate_id,
        "aggregateVersion": event.aggregate_version,
        "correlationId": event.correlation_id,
        "occurredAt": event.occurred_at.isoformat(),
        "payload": event.payload,
    }
