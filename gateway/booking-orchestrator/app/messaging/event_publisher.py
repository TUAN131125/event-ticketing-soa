from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.domain.errors import EsbError
from app.domain.models import RequestContext


class TopicPublisher:
    """Routes a known event topic to its configured subscriber adapters."""

    def __init__(self, subscribers: Mapping[str, Sequence[Any]]) -> None:
        self.subscribers = {
            topic: tuple(targets)
            for topic, targets in subscribers.items()
        }

    async def publish(
        self,
        topic: str,
        payload: dict[str, Any],
        message_id: str,
        ctx: RequestContext | None = None,
    ) -> None:
        targets = self.subscribers.get(topic)
        if targets is None:
            raise EsbError(
                "UNKNOWN_EVENT_TOPIC",
                f"No subscriber mapping for {topic}",
                500,
            )
        for target in targets:
            await target.publish(topic, payload, message_id, ctx)
