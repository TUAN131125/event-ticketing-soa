from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol

from app.domain.models import (
    IdempotencyDecision,
    OperationResult,
    OutboxItem,
    WorkflowEvidence,
)


class WorkflowRepository(Protocol):
    async def create(self, workflow: WorkflowEvidence) -> None: ...
    async def get(self, workflow_id: str) -> WorkflowEvidence | None: ...
    async def save(self, workflow: WorkflowEvidence) -> None: ...
    async def record_step(
        self,
        workflow_id: str,
        step: str,
        provider: str,
        outcome: str,
        safe_details: Mapping[str, Any],
    ) -> None: ...
    async def recoverable(self) -> Sequence[WorkflowEvidence]: ...


class IdempotencyRepository(Protocol):
    async def claim(self, operation: str, subject: str, key: str, request_hash: str) -> IdempotencyDecision: ...
    async def complete(self, operation: str, subject: str, key: str, result: OperationResult) -> None: ...


class TraceRepository(Protocol):
    async def append(
        self,
        correlation_id: str,
        service: str,
        operation: str,
        status: str,
        duration_ms: int,
        error_code: str | None = None,
    ) -> None: ...
    async def list(self, correlation_id: str) -> Sequence[Mapping[str, Any]]: ...


class OutboxRepository(Protocol):
    async def commit_with_outbox(self, workflow: WorkflowEvidence, items: Sequence[OutboxItem]) -> None: ...
    async def enqueue_many(self, workflow_id: str, items: Sequence[OutboxItem]) -> None: ...
    async def due_outbox(self, now: datetime, limit: int) -> Sequence[Mapping[str, Any]]: ...
    async def delivered(self, message_id: str) -> None: ...
    async def failed(self, message_id: str, next_attempt_at: datetime, error_code: str) -> None: ...


class ReconciliationRepository(Protocol):
    async def schedule(
        self,
        workflow_id: str,
        kind: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        deadline: datetime | None = None,
    ) -> None: ...
    async def due_jobs(self, now: datetime, limit: int, lease_until: datetime | None = None) -> Sequence[Mapping[str, Any]]:
        """Claim due jobs. Concurrent workers must never receive the same job."""
        ...

    async def complete_job(self, job_id: str) -> None: ...
    async def reschedule_job(self, job_id: str, next_attempt_at: datetime, evidence: Mapping[str, Any]) -> None: ...
    async def abandon_job(self, job_id: str, evidence: Mapping[str, Any]) -> None:
        """Stop retrying past the deadline without inventing a payment outcome."""
        ...


class Clock(Protocol):
    def now(self) -> datetime: ...
    def monotonic(self) -> float: ...
