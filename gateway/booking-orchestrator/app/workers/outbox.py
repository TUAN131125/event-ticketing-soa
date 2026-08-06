from __future__ import annotations

import asyncio
import time
from typing import Any


class OutboxWorker:
    """Dispatches durable outbox messages with bounded retry and dead-lettering."""

    def __init__(
        self,
        repo: Any,
        publisher: Any,
        max_attempts: int = 8,
        batch_size: int = 50,
    ) -> None:
        self.repo = repo
        self.publisher = publisher
        self.max_attempts = max_attempts
        self.batch_size = batch_size

    async def run_once(self) -> int:
        messages = await self.repo.due(self.batch_size)
        for message in messages:
            try:
                await self.publisher.publish(
                    message.topic,
                    message.payload,
                    message.message_id,
                )
                message.state = "SENT"
                message.last_error = None
            except Exception as exc:
                message.attempts += 1
                message.last_error = str(exc)[:1000]
                if message.attempts >= self.max_attempts:
                    message.state = "DEAD_LETTER"
                else:
                    message.next_attempt_at = time.time() + min(
                        300,
                        2 ** message.attempts,
                    )
            await self.repo.save_message(message)
        return len(messages)

    async def run_forever(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
