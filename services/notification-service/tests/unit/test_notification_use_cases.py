from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from libs.platform_security import sign_hmac_request

from app.config import Settings
from app.dependencies import get_provider, get_repository
from app.infrastructure.database.repositories import InMemoryDeliveryRepository
from app.main import create_app


class RecordingProvider:
    def __init__(self) -> None:
        self.recipients: list[str] = []

    def send(self, to: str, subject: str, body: str) -> None:
        del subject, body
        self.recipients.append(to)


def _body() -> bytes:
    return json.dumps(
        {
            "eventId": "evt-webhook-1",
            "eventType": "booking.confirmed",
            "schemaVersion": 1,
            "occurredAt": "2026-08-05T03:00:00Z",
            "correlationId": "corr-notification-1",
            "aggregateId": "BKG-1",
            "data": {"customerEmail": "customer@example.com"},
        },
        separators=(",", ":"),
    ).encode()


def test_webhook_hmac_accepts_once_and_rejects_replay(
    notification_settings: Settings,
) -> None:
    repo = InMemoryDeliveryRepository()
    provider = RecordingProvider()
    app = create_app(notification_settings)
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_provider] = lambda: provider
    body = _body()
    timestamp = datetime.now(UTC).isoformat()
    signature = sign_hmac_request(
        notification_settings.webhook_hmac_secret, timestamp, body
    )
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Timestamp": timestamp,
        "X-Webhook-Signature": f"sha256={signature}",
    }
    with TestClient(app) as client:
        accepted = client.post("/webhooks/events", content=body, headers=headers)
        replay = client.post("/webhooks/events", content=body, headers=headers)
    assert accepted.status_code == 202
    assert replay.status_code == 401
    assert provider.recipients == ["customer@example.com"]
    assert repo.get_by_event_id("evt-webhook-1") is not None


def test_webhook_rejects_missing_and_invalid_signature(
    notification_settings: Settings,
) -> None:
    app = create_app(notification_settings)
    with TestClient(app) as client:
        missing = client.post("/webhooks/events", content=_body())
        invalid = client.post(
            "/webhooks/events",
            content=_body(),
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Timestamp": datetime.now(UTC).isoformat(),
                "X-Webhook-Signature": "sha256=invalid",
            },
        )
    assert missing.status_code == 401
    assert invalid.status_code == 401
