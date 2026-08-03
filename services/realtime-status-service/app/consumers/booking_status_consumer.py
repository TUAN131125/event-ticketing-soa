"""Bounded deduplication and sequence projection for incoming events."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from app.broadcast.backends import BroadcastBackend
from app.observability.metrics import DUPLICATE_EVENTS, EVENTS_ACCEPTED, SEQUENCE_GAPS, STALE_EVENTS
from app.schemas.messages import RealtimeStatusEvent


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    outcome: Literal["accepted", "duplicate", "stale", "no_subscribers"]
    broadcast: bool
    sequence_gap: bool


class StatusEventProcessor:
    def __init__(
        self,
        backend: BroadcastBackend,
        *,
        dedup_ttl: float,
        dedup_max_entries: int,
        sequence_ttl: float,
        sequence_max_entries: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._backend = backend
        self._dedup_ttl = dedup_ttl
        self._dedup_max_entries = dedup_max_entries
        self._sequence_ttl = sequence_ttl
        self._sequence_max_entries = sequence_max_entries
        self._clock = clock
        self._message_ids: OrderedDict[str, float] = OrderedDict()
        self._sequences: OrderedDict[str, tuple[int, float]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def process(self, event: RealtimeStatusEvent) -> ProcessingResult:
        async with self._lock:
            self._cleanup_locked()
            if event.message_id in self._message_ids:
                DUPLICATE_EVENTS.inc()
                return ProcessingResult("duplicate", False, False)
            current = self._sequences.get(event.booking_id)
            if current is not None and event.sequence <= current[0]:
                self._remember_message(event.message_id)
                STALE_EVENTS.inc()
                return ProcessingResult("stale", False, False)
            expected = current[0] + 1 if current else 1
            gap = event.sequence > expected
            self._remember_message(event.message_id)
            now = self._clock()
            self._sequences[event.booking_id] = (event.sequence, now)
            self._sequences.move_to_end(event.booking_id)
            while len(self._sequences) > self._sequence_max_entries:
                self._sequences.popitem(last=False)
        if gap:
            SEQUENCE_GAPS.inc()
        try:
            result = await self._backend.publish(
                event, sequence_gap=gap, expected_sequence=expected if gap else None
            )
        except (RuntimeError, OSError):
            async with self._lock:
                self._message_ids.pop(event.message_id, None)
                current_after_failure = self._sequences.get(event.booking_id)
                if current_after_failure is not None and current_after_failure[0] == event.sequence:
                    if current is None:
                        self._sequences.pop(event.booking_id, None)
                    else:
                        self._sequences[event.booking_id] = current
            raise
        EVENTS_ACCEPTED.inc()
        return ProcessingResult(
            "no_subscribers" if result.subscribers == 0 else "accepted", result.delivered > 0, gap
        )

    def _remember_message(self, message_id: str) -> None:
        self._message_ids[message_id] = self._clock()
        self._message_ids.move_to_end(message_id)
        while len(self._message_ids) > self._dedup_max_entries:
            self._message_ids.popitem(last=False)

    async def cleanup(self) -> None:
        async with self._lock:
            self._cleanup_locked()

    def _cleanup_locked(self) -> None:
        now = self._clock()
        message_cutoff = now - self._dedup_ttl
        while self._message_ids and next(iter(self._message_ids.values())) <= message_cutoff:
            self._message_ids.popitem(last=False)
        sequence_cutoff = now - self._sequence_ttl
        while self._sequences and next(iter(self._sequences.values()))[1] <= sequence_cutoff:
            self._sequences.popitem(last=False)

    async def last_sequence(self, booking_id: str) -> int | None:
        async with self._lock:
            self._cleanup_locked()
            item = self._sequences.get(booking_id)
            return item[0] if item else None

    async def sizes(self) -> tuple[int, int]:
        async with self._lock:
            return len(self._message_ids), len(self._sequences)
