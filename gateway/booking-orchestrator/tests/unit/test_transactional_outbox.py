from __future__ import annotations

import tempfile

import pytest

from app.domain.models import OutboxMessage, Workflow
from app.persistence.repositories import SqliteRepository


@pytest.mark.asyncio
async def test_sqlite_saves_confirmed_workflow_and_outbox_in_one_repository_call() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as database:
        repository = SqliteRepository(f"sqlite:///{database.name}")
        workflow = Workflow(
            workflow_id="wf-1",
            idempotency_key="idem-transactional-outbox",
            request_hash="hash",
            customer_id="cust-1",
            event_id="event-1",
            seat_ids=["A1"],
            evidence={"correlationId": "corr-1"},
        )
        messages = [
            OutboxMessage("msg-1", "booking.confirmed", {"bookingId": "b1"}),
            OutboxMessage("msg-2", "booking.status", {"bookingId": "b1"}),
        ]

        await repository.save_with_outbox(workflow, messages)

        stored = await repository.get("wf-1")
        due = await repository.due(10)
        assert stored is not None
        assert {message.message_id for message in due} == {"msg-1", "msg-2"}
