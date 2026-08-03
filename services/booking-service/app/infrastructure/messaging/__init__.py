"""Transactional outbox integration boundary.

Commands persist events in ``booking.outbox_events``. A deployment-specific
relay can publish them at least once without coupling domain transactions to a
particular broker.
"""

from app.infrastructure.messaging.envelope import outbox_event_envelope

__all__ = ["outbox_event_envelope"]
