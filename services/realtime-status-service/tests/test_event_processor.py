from __future__ import annotations

from typing import Any

import pytest

from app.consumers.booking_status_consumer import StatusEventProcessor
from app.schemas.messages import RealtimeStatusEvent
from app.websocket.connection_manager import BroadcastResult
from tests.conftest import event


class FakeBackend:
    name = "fake"

    def __init__(self, subscribers: int = 1) -> None:
        self.events: list[tuple[RealtimeStatusEvent, bool, int | None]] = []
        self.subscribers = subscribers

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def ready(self) -> bool:
        return True

    def availability(self) -> str:
        return "not_configured"

    async def publish(
        self,
        value: RealtimeStatusEvent,
        *,
        sequence_gap: bool = False,
        expected_sequence: int | None = None,
    ) -> BroadcastResult:
        self.events.append((value, sequence_gap, expected_sequence))
        return BroadcastResult(self.subscribers, self.subscribers, 0)


def status(**changes: Any) -> RealtimeStatusEvent:
    payload = event()
    payload.update(changes)
    return RealtimeStatusEvent.model_validate(payload)


@pytest.mark.asyncio
async def test_dedup_stale_and_gap_rules() -> None:
    backend = FakeBackend()
    processor = StatusEventProcessor(
        backend, dedup_ttl=10, dedup_max_entries=10, sequence_ttl=10, sequence_max_entries=10
    )
    assert (await processor.process(status())).outcome == "accepted"
    assert (await processor.process(status())).outcome == "duplicate"
    assert (await processor.process(status(messageId="msg-stale", sequence=1))).outcome == "stale"
    gap = await processor.process(status(messageId="msg-gap", sequence=3))
    assert gap.sequence_gap is True
    assert backend.events[-1][1:] == (True, 2)
    assert len(backend.events) == 2


@pytest.mark.asyncio
async def test_no_subscribers_is_distinct() -> None:
    processor = StatusEventProcessor(
        FakeBackend(0), dedup_ttl=10, dedup_max_entries=2, sequence_ttl=10, sequence_max_entries=2
    )
    result = await processor.process(status())
    assert result.outcome == "no_subscribers"
    assert result.broadcast is False


@pytest.mark.asyncio
async def test_caches_are_ttl_and_size_bounded() -> None:
    now = [0.0]
    processor = StatusEventProcessor(
        FakeBackend(),
        dedup_ttl=5,
        dedup_max_entries=2,
        sequence_ttl=5,
        sequence_max_entries=2,
        clock=lambda: now[0],
    )
    for index in range(1, 4):
        await processor.process(status(messageId=f"msg-{index}", bookingId=f"BK-{index}"))
    assert await processor.sizes() == (2, 2)
    now[0] = 6
    await processor.cleanup()
    assert await processor.sizes() == (0, 0)


@pytest.mark.asyncio
async def test_publish_failure_does_not_poison_retry_dedup_state() -> None:
    class FailOnceBackend(FakeBackend):
        async def publish(
            self,
            value: RealtimeStatusEvent,
            *,
            sequence_gap: bool = False,
            expected_sequence: int | None = None,
        ) -> BroadcastResult:
            if not self.events:
                self.events.append((value, sequence_gap, expected_sequence))
                raise RuntimeError("backend down")
            return await super().publish(
                value, sequence_gap=sequence_gap, expected_sequence=expected_sequence
            )

    processor = StatusEventProcessor(
        FailOnceBackend(),
        dedup_ttl=10,
        dedup_max_entries=10,
        sequence_ttl=10,
        sequence_max_entries=10,
    )
    with pytest.raises(RuntimeError, match="backend down"):
        await processor.process(status())
    assert (await processor.process(status())).outcome == "accepted"
