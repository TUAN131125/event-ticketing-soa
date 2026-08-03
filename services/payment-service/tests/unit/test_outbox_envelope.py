from datetime import UTC, datetime

from app.infrastructure.database.models import OutboxEventModel
from app.infrastructure.messaging import outbox_event_envelope


def test_outbox_row_maps_to_the_shared_event_envelope() -> None:
    occurred_at = datetime.now(UTC)
    row = OutboxEventModel(
        event_id="4a672792-f194-4a9d-9023-9bad17fec51a",
        aggregate_id="PAY00000001",
        aggregate_type="Payment",
        aggregate_version=1,
        event_type="payment.created",
        payload={"paymentId": "PAY00000001"},
        correlation_id="COR-1",
        occurred_at=occurred_at,
    )

    assert outbox_event_envelope(row) == {
        "eventId": row.event_id,
        "eventType": "payment.created",
        "aggregateType": "Payment",
        "aggregateId": "PAY00000001",
        "aggregateVersion": 1,
        "correlationId": "COR-1",
        "occurredAt": occurred_at.isoformat(),
        "payload": {"paymentId": "PAY00000001"},
    }
