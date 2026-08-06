"""Broker-neutral publication of outbox envelopes.

Payment Service owns the envelope, not the transport. The relay depends on the
EventPublisher port only, so swapping the webhook adapter for Kafka, SQS or
RabbitMQ later needs no change in the application or domain layers.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Protocol

LOGGER = logging.getLogger("payment.outbox")
SIGNATURE_SEPARATOR = "."


class PublishFailed(Exception):
    """The envelope could not be delivered; the relay will retry it later."""


class EventPublisher(Protocol):
    def publish(self, envelope: dict[str, Any]) -> None: ...


class LoggingEventPublisher:
    """Default publisher: records the envelope instead of sending it anywhere.

    Used when no destination is configured, so a local or demo deployment still
    drains the outbox and shows the exact envelope a broker would receive.
    """

    def publish(self, envelope: dict[str, Any]) -> None:
        LOGGER.info(
            "Outbox event published to log sink",
            extra={
                "operation": "outbox.publish",
                "result": "LOGGED",
                "event_id": envelope["eventId"],
                "event_type": envelope["eventType"],
            },
        )


class WebhookEventPublisher:
    """POST the envelope to an event ingress, signed with a shared secret.

    The signature covers timestamp and raw body exactly as the integration
    contract requires, so a receiver can reject replays and forged payloads.
    """

    def __init__(self, url: str, secret: str, timeout_seconds: int) -> None:
        if not url.startswith(("http://", "https://")):
            raise ValueError("Outbox webhook URL must be an http(s) URL")
        if not secret:
            raise ValueError("Outbox webhook secret must not be empty")
        self._url = url
        self._secret = secret.encode("utf-8")
        self._timeout_seconds = timeout_seconds

    def publish(self, envelope: dict[str, Any]) -> None:
        body = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
        timestamp = str(int(time.time()))
        request = urllib.request.Request(  # noqa: S310 - scheme checked in __init__
            self._url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Timestamp": timestamp,
                "X-Webhook-Signature": self._signature(timestamp, body),
                "X-Correlation-ID": str(envelope["correlationId"]),
            },
        )
        try:
            with urllib.request.urlopen(  # noqa: S310 - scheme checked in __init__
                request, timeout=self._timeout_seconds
            ) as response:
                if response.status >= 300:
                    raise PublishFailed(f"Receiver returned HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            raise PublishFailed(f"Receiver returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            # Deliberately drops the URL: it is recorded on the event row and
            # must never carry credentials into an error message.
            raise PublishFailed(f"Receiver unreachable: {type(exc).__name__}") from exc
        except TimeoutError as exc:
            raise PublishFailed("Receiver timed out") from exc

    def _signature(self, timestamp: str, body: bytes) -> str:
        payload = timestamp.encode("utf-8") + SIGNATURE_SEPARATOR.encode() + body
        return hmac.new(self._secret, payload, hashlib.sha256).hexdigest()
