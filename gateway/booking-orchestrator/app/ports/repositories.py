from __future__ import annotations

from typing import Protocol

from app.domain.models import OutboxMessage, Workflow


class WorkflowRepository(Protocol):
    async def find_by_idempotency(self, key: str) -> Workflow | None: ...

    async def get(self, workflow_id: str) -> Workflow | None: ...

    async def save(self, workflow: Workflow) -> None: ...

    async def save_with_outbox(
        self,
        workflow: Workflow,
        messages: list[OutboxMessage],
    ) -> None: ...

    async def find_by_correlation(self, correlation_id: str) -> Workflow | None: ...

    async def list_by_status(
        self,
        status: str,
        limit: int = 100,
    ) -> list[Workflow]: ...


class OutboxRepository(Protocol):
    async def add(self, message: OutboxMessage) -> None: ...

    async def due(self, limit: int) -> list[OutboxMessage]: ...

    async def save_message(self, message: OutboxMessage) -> None: ...
