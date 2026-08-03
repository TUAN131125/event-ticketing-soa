"""Transactional outbox integration boundary."""

from app.infrastructure.messaging.envelope import outbox_event_envelope

__all__ = ["outbox_event_envelope"]
