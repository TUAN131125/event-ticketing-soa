"""Relay behaviour that needs no database: publisher selection and signing."""

import dataclasses
import hashlib
import hmac
import json
import threading
from collections.abc import Iterator
from email.message import Message
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.application.outbox import RelayResult, create_publisher
from app.config import Settings
from app.infrastructure.messaging.publisher import (
    LoggingEventPublisher,
    PublishFailed,
    WebhookEventPublisher,
)
from tests.factories import build_settings

SECRET = "s" * 32
ENVELOPE = {
    "eventId": "11111111-2222-3333-4444-555555555555",
    "eventType": "payment.succeeded",
    "aggregateType": "Payment",
    "aggregateId": "PAY00000001",
    "aggregateVersion": 3,
    "correlationId": "COR-1",
    "occurredAt": "2026-08-05T10:00:00+00:00",
    "payload": {"paymentId": "PAY00000001"},
}


class _Receiver(BaseHTTPRequestHandler):
    status_code = 200
    # Message, not dict: urllib normalises header casing and HTTP header names
    # are case-insensitive, so lookups must be too.
    received: list[tuple[Message, bytes]] = []

    def do_POST(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        body = self.rfile.read(int(self.headers["Content-Length"]))
        type(self).received.append((self.headers, body))
        self.send_response(type(self).status_code)
        self.end_headers()

    def log_message(self, *_args: object) -> None:
        """Keep the test output clean."""


@pytest.fixture
def receiver() -> Iterator[HTTPServer]:
    _Receiver.received = []
    _Receiver.status_code = 200
    server = HTTPServer(("127.0.0.1", 0), _Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def url_for(server: HTTPServer) -> str:
    host, port = server.server_address[0], server.server_address[1]
    return f"http://{host}:{port}/events"


def test_relay_result_counts_everything_it_touched() -> None:
    assert RelayResult(published=3, failed=2).processed == 5
    assert RelayResult(published=0, failed=0).processed == 0


def test_publisher_defaults_to_the_log_sink_without_a_webhook_url() -> None:
    assert isinstance(create_publisher(build_settings()), LoggingEventPublisher)


def test_publisher_uses_the_webhook_when_a_url_is_configured() -> None:
    configured = dataclasses.replace(
        build_settings(),
        outbox_webhook_url="https://esb.internal/events",
        outbox_webhook_secret=SECRET,
    )
    assert isinstance(create_publisher(configured), WebhookEventPublisher)


def test_webhook_publisher_rejects_an_unsafe_destination() -> None:
    with pytest.raises(ValueError, match="http"):
        WebhookEventPublisher("file:///etc/passwd", SECRET, 5)
    with pytest.raises(ValueError, match="secret"):
        WebhookEventPublisher("https://esb.internal/events", "", 5)


def test_webhook_delivers_a_signed_envelope(receiver: HTTPServer) -> None:
    WebhookEventPublisher(url_for(receiver), SECRET, 5).publish(ENVELOPE)

    assert len(_Receiver.received) == 1
    headers, body = _Receiver.received[0]
    assert json.loads(body) == ENVELOPE
    assert headers["X-Correlation-ID"] == "COR-1"

    timestamp = headers["X-Webhook-Timestamp"]
    expected = hmac.new(
        SECRET.encode("utf-8"),
        f"{timestamp}.".encode() + body,
        hashlib.sha256,
    ).hexdigest()
    assert headers["X-Webhook-Signature"] == expected


def test_receiver_error_is_reported_as_a_retryable_failure(
    receiver: HTTPServer,
) -> None:
    _Receiver.status_code = 500
    publisher = WebhookEventPublisher(url_for(receiver), SECRET, 5)
    with pytest.raises(PublishFailed, match="500"):
        publisher.publish(ENVELOPE)


def test_unreachable_receiver_is_reported_as_a_retryable_failure() -> None:
    publisher = WebhookEventPublisher(
        "http://127.0.0.1:9/unreachable", SECRET, timeout_seconds=1
    )
    with pytest.raises(PublishFailed):
        publisher.publish(ENVELOPE)


def test_settings_reject_a_webhook_without_a_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAYMENT_APP_ENV", "local")
    monkeypatch.setenv("PAYMENT_OUTBOX_WEBHOOK_URL", "https://esb.internal/events")
    monkeypatch.delenv("PAYMENT_OUTBOX_WEBHOOK_SECRET", raising=False)
    with pytest.raises(ValueError, match="SECRET"):
        Settings.from_environment()
