"""In-process and optional Redis pub/sub broadcast implementations."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from collections import OrderedDict
from typing import Any, Protocol

from redis.exceptions import RedisError

from app.observability.metrics import BROADCAST_ATTEMPTS, BROADCAST_FAILURES
from app.schemas.messages import RealtimeStatusEvent, ResyncRequiredControl
from app.websocket.connection_manager import BroadcastResult, ConnectionManager

LOGGER = logging.getLogger("realtime.broadcast")


class BroadcastBackend(Protocol):
    name: str

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def publish(
        self,
        event: RealtimeStatusEvent,
        *,
        sequence_gap: bool = False,
        expected_sequence: int | None = None,
    ) -> BroadcastResult: ...
    def ready(self) -> bool: ...
    def availability(self) -> str: ...


class InMemoryBroadcastBackend:
    name = "memory"

    def __init__(self, manager: ConnectionManager, authoritative_url_template: str) -> None:
        self._manager = manager
        self._authoritative_url_template = authoritative_url_template

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def ready(self) -> bool:
        return True

    def availability(self) -> str:
        return "not_configured"

    async def publish(
        self,
        event: RealtimeStatusEvent,
        *,
        sequence_gap: bool = False,
        expected_sequence: int | None = None,
    ) -> BroadcastResult:
        BROADCAST_ATTEMPTS.labels(self.name).inc()
        if sequence_gap:
            control = ResyncRequiredControl(
                bookingId=event.booking_id,
                reason="sequence_gap",
                authoritativeUrl=self._authoritative_url_template.replace(
                    "{bookingId}", event.booking_id
                ),
                expectedSequence=expected_sequence,
                observedSequence=event.sequence,
            ).model_dump(by_alias=True, mode="json")
            await self._manager.broadcast(event.booking_id, control)
        return await self._manager.broadcast(event.booking_id, event.wire())


class RedisBroadcastBackend:
    """Non-durable Redis pub/sub with reconnect and per-instance delivery dedup."""

    name = "redis"

    def __init__(
        self,
        manager: ConnectionManager,
        *,
        redis_url: str,
        channel: str,
        authoritative_url_template: str,
        dedup_ttl: int,
        dedup_max_entries: int,
    ) -> None:
        self._manager = manager
        self._url = redis_url
        self._channel = channel
        self._authoritative_url_template = authoritative_url_template
        self._dedup_ttl = dedup_ttl
        self._dedup_max_entries = dedup_max_entries
        self._redis: Any | None = None
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self._subscribed = asyncio.Event()
        self._available = False
        self._delivered: OrderedDict[str, float] = OrderedDict()
        self._last_result: dict[str, BroadcastResult] = {}
        self._waiters: dict[str, asyncio.Future[BroadcastResult]] = {}

    async def start(self) -> None:
        try:
            import redis.asyncio as redis
        except ImportError as exc:
            raise RuntimeError(
                "Redis backend configured but redis dependency is unavailable"
            ) from exc
        self._redis = redis.from_url(
            self._url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
        )
        self._task = asyncio.create_task(self._consume(), name="redis-status-consumer")
        try:
            await asyncio.wait_for(self._redis.ping(), timeout=2)
            await asyncio.wait_for(self._subscribed.wait(), timeout=2)
            self._available = True
        except (TimeoutError, OSError, RedisError):
            self._available = False

    async def stop(self) -> None:
        self._stopping.set()
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        if self._redis is not None:
            await self._redis.aclose()
        self._available = False

    def ready(self) -> bool:
        return self._available

    def availability(self) -> str:
        return "available" if self._available else "unavailable"

    async def publish(
        self,
        event: RealtimeStatusEvent,
        *,
        sequence_gap: bool = False,
        expected_sequence: int | None = None,
    ) -> BroadcastResult:
        BROADCAST_ATTEMPTS.labels(self.name).inc()
        if self._redis is None or not self._available:
            BROADCAST_FAILURES.labels(self.name).inc()
            raise RuntimeError("Redis broadcast is unavailable")
        payload = json.dumps(
            {
                "event": event.wire(),
                "sequenceGap": sequence_gap,
                "expectedSequence": expected_sequence,
            },
            separators=(",", ":"),
        )
        waiter = asyncio.get_running_loop().create_future()
        self._waiters[event.message_id] = waiter
        try:
            await self._redis.publish(self._channel, payload)
            return await asyncio.wait_for(waiter, timeout=2)
        except (TimeoutError, OSError, RedisError) as exc:
            BROADCAST_FAILURES.labels(self.name).inc()
            self._available = False
            raise RuntimeError("Redis publish failed") from exc
        finally:
            self._waiters.pop(event.message_id, None)

    async def _consume(self) -> None:
        backoff = 0.25
        while not self._stopping.is_set():
            pubsub = None
            try:
                if self._redis is None:
                    return
                pubsub = self._redis.pubsub()
                await pubsub.subscribe(self._channel)
                self._subscribed.set()
                self._available = True
                backoff = 0.25
                async for message in pubsub.listen():
                    if self._stopping.is_set():
                        return
                    if message.get("type") == "message":
                        await self._deliver(str(message.get("data", "")))
            except asyncio.CancelledError:
                raise
            except (
                OSError,
                RedisError,
                RuntimeError,
                ValueError,
                TypeError,
                KeyError,
                json.JSONDecodeError,
            ):
                self._available = False
                self._subscribed.clear()
                delay = min(backoff, 5.0) + random.random() * 0.1  # noqa: S311 - jitter is not security-sensitive
                await asyncio.sleep(delay)
                backoff = min(backoff * 2, 5.0)
            finally:
                if pubsub is not None:
                    await pubsub.aclose()

    async def _deliver(self, raw: str) -> None:
        envelope = json.loads(raw)
        event = RealtimeStatusEvent.model_validate(envelope["event"])
        now = time.monotonic()
        cutoff = now - self._dedup_ttl
        while self._delivered and next(iter(self._delivered.values())) <= cutoff:
            self._delivered.popitem(last=False)
        if event.message_id in self._delivered:
            return
        self._delivered[event.message_id] = now
        while len(self._delivered) > self._dedup_max_entries:
            self._delivered.popitem(last=False)
        if envelope.get("sequenceGap"):
            control = ResyncRequiredControl(
                bookingId=event.booking_id,
                reason="sequence_gap",
                authoritativeUrl=self._authoritative_url_template.replace(
                    "{bookingId}", event.booking_id
                ),
                expectedSequence=envelope.get("expectedSequence"),
                observedSequence=event.sequence,
            ).model_dump(by_alias=True, mode="json")
            await self._manager.broadcast(event.booking_id, control)
        result = await self._manager.broadcast(event.booking_id, event.wire())
        waiter = self._waiters.get(event.message_id)
        if waiter is not None and not waiter.done():
            waiter.set_result(result)
