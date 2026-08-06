from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from app.adapters.rest.providers import NotificationWebhookSubscriber
from app.config import Settings
from app.registry.service_registry import ServiceRegistry


class CapturingClient:
    def __init__(self) -> None:
        self.call: dict | None = None

    async def request(self, method, path, context, **kwargs):
        self.call = {
            "method": method,
            "path": path,
            "context": context,
            **kwargs,
        }
        return {}


@pytest.mark.asyncio
async def test_notification_webhook_uses_contract_envelope_and_hmac() -> None:
    client = CapturingClient()
    secret = "notification-secret-with-at-least-32-characters"
    subscriber = NotificationWebhookSubscriber(client, secret)

    await subscriber.publish(
        "booking.confirmed",
        {
            "bookingId": "BKG-001",
            "status": "CONFIRMED",
            "correlationId": "corr-001",
            "traceId": "1" * 32,
        },
        "MSG-001",
    )

    assert client.call is not None
    assert client.call["method"] == "POST"
    assert client.call["path"] == "/webhooks/events"
    body = json.loads(client.call["content"])
    assert body["eventId"] == "MSG-001"
    assert body["eventType"] == "booking.confirmed"
    assert body["aggregateId"] == "BKG-001"

    timestamp = client.call["headers"]["X-Webhook-Timestamp"]
    expected = hmac.new(
        secret.encode(),
        timestamp.encode() + b"." + client.call["content"],
        hashlib.sha256,
    ).hexdigest()
    assert client.call["headers"]["X-Webhook-Signature"] == f"sha256={expected}"


def test_seat_readiness_uses_rest_base_not_soap_endpoint() -> None:
    registry = ServiceRegistry(
        Settings(seat_service_url="http://seat-inventory-service:8003/soap")
    )
    assert (
        registry.resolve("seat").readiness_url
        == "http://seat-inventory-service:8003/health/ready"
    )

@pytest.mark.asyncio
async def test_readiness_checks_only_esb_database() -> None:
    class Repository:
        async def list_by_status(self, status, limit=1):
            assert status == "STARTED"
            assert limit == 1
            return []

    from app.application.health import AggregateHealthService

    health = AggregateHealthService(registry=None, repository=Repository())
    status, payload = await health.ready()
    assert status == 200
    assert payload == {
        "status": "READY",
        "service": "booking-orchestrator",
        "version": "2.0.0",
    }
