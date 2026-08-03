from __future__ import annotations

from datetime import timedelta
from time import monotonic

from app.domain.models import Principal, RequestContext
from app.ports.providers import NotificationPort, RealtimePort
from app.ports.repositories import Clock, OutboxRepository


class OutboxDispatcher:
    def __init__(
        self,
        repository: OutboxRepository,
        notification: NotificationPort,
        realtime: RealtimePort,
        clock: Clock,
    ) -> None:
        self.repository, self.notification, self.realtime, self.clock = (
            repository,
            notification,
            realtime,
            clock,
        )

    async def run_once(self, limit: int = 50) -> int:
        messages = await self.repository.due_outbox(self.clock.now(), limit)
        for message in messages:
            context = RequestContext(
                str(message["correlationId"]),
                None,
                monotonic() + 10,
                Principal("booking-orchestrator", ("SERVICE",)),
            )
            try:
                adapter = self.notification if message["destination"] == "notification" else self.realtime
                await adapter.publish(message["payload"], str(message["messageId"]), context)
                await self.repository.delivered(str(message["messageId"]))
            except Exception:  # noqa: BLE001 -- durable retry records every delivery failure
                attempts = int(message.get("attempts", 0)) + 1
                await self.repository.failed(
                    str(message["messageId"]),
                    self.clock.now() + timedelta(seconds=min(300, 2**attempts)),
                    "SIDE_EFFECT_DELIVERY_FAILED",
                )
        return len(messages)
