"""Transactional outbox relay use case."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from app.application.common import prepare_transaction
from app.application.queries.outbox_backlog import outbox_backlog
from app.config import Settings
from app.infrastructure.database.repositories import (
    claim_next_outbox_event,
    database_now,
    mark_outbox_failed,
    mark_outbox_published,
)
from app.infrastructure.messaging.envelope import outbox_event_envelope
from app.infrastructure.messaging.publisher import (
    EventPublisher,
    LoggingEventPublisher,
    PublishFailed,
    WebhookEventPublisher,
)
from app.observability.metrics import (
    OUTBOX_EXHAUSTED,
    OUTBOX_PENDING,
    OUTBOX_PUBLISH_TOTAL,
)

LOGGER = logging.getLogger("payment.outbox")


@dataclass(frozen=True, slots=True)
class RelayResult:
    published: int
    failed: int

    @property
    def processed(self) -> int:
        return self.published + self.failed


@dataclass(frozen=True, slots=True)
class OutboxBacklog:
    pending: int
    exhausted: int


class OutboxRelay:
    """Drains payment.outbox_events to the configured publisher.

    Delivery is at-least-once: an event is marked published only after the
    publisher returns, so a crash between sending and committing replays it.
    Consumers therefore have to deduplicate on eventId.
    """

    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        publisher: EventPublisher,
    ) -> None:
        self._settings = settings
        self._sessions = session_factory
        self._publisher = publisher

    def run_once(self) -> RelayResult:
        """Publish up to one batch, stopping early when the queue drains."""
        published = 0
        failed = 0
        for _ in range(self._settings.outbox_batch_size):
            outcome = self._relay_next()
            if outcome is None:
                break
            if outcome:
                published += 1
            else:
                failed += 1
        return RelayResult(published=published, failed=failed)

    def backlog(self) -> OutboxBacklog:
        with self._sessions() as session:
            pending, exhausted = outbox_backlog(session, self._settings)
        return OutboxBacklog(pending=pending, exhausted=exhausted)

    def refresh_backlog_gauges(self) -> None:
        backlog = self.backlog()
        OUTBOX_PENDING.set(backlog.pending)
        OUTBOX_EXHAUSTED.set(backlog.exhausted)

    def _relay_next(self) -> bool | None:
        """Publish the next event: True sent, False failed, None queue empty.

        One transaction per event keeps the row lock held for a single publish
        attempt instead of a whole batch of them.
        """
        with self._sessions() as session, session.begin():
            prepare_transaction(session, self._settings)
            event = claim_next_outbox_event(
                session, max_attempts=self._settings.outbox_max_attempts
            )
            if event is None:
                return None
            event_id = event.event_id
            event_type = event.event_type
            try:
                self._publisher.publish(outbox_event_envelope(event))
            except PublishFailed as error:
                mark_outbox_failed(event, str(error))
                OUTBOX_PUBLISH_TOTAL.labels(event_type, "failure").inc()
                LOGGER.warning(
                    "Outbox event publication failed",
                    extra={
                        "operation": "outbox.publish",
                        "result": "RETRY",
                        "event_id": event_id,
                        "event_type": event_type,
                        "attempts": event.publish_attempts,
                    },
                )
                return False
            mark_outbox_published(event, database_now(session))
            OUTBOX_PUBLISH_TOTAL.labels(event_type, "success").inc()
            return True


def create_publisher(settings: Settings) -> EventPublisher:
    """Pick the publisher the configuration asks for."""
    if not settings.outbox_webhook_enabled:
        return LoggingEventPublisher()
    return WebhookEventPublisher(
        settings.outbox_webhook_url,
        settings.outbox_webhook_secret,
        settings.outbox_webhook_timeout_seconds,
    )
