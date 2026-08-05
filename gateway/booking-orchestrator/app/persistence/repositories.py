from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select

from app.domain.errors import IdempotencyConflict
from app.domain.models import (
    IdempotencyDecision,
    Money,
    OperationResult,
    OutboxItem,
    PaymentOutcome,
    WorkflowEvidence,
    WorkflowPhase,
)
from app.persistence.database import Database
from app.persistence.models import (
    IdempotencyRow,
    OutboxRow,
    ReconciliationRow,
    TraceStepRow,
    WorkflowRow,
    WorkflowStepRow,
)


class SqlRepositories:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create(self, workflow: WorkflowEvidence) -> None:
        async with self.database.sessions.begin() as session:
            if await session.get(WorkflowRow, workflow.workflow_id) is None:
                session.add(self._to_row(workflow))

    async def get(self, workflow_id: str) -> WorkflowEvidence | None:
        async with self.database.sessions() as session:
            row = await session.get(WorkflowRow, workflow_id)
            return self._from_row(row) if row else None

    async def save(self, workflow: WorkflowEvidence) -> None:
        async with self.database.sessions.begin() as session:
            row = await session.get(WorkflowRow, workflow.workflow_id, with_for_update=True)
            if row is None:
                session.add(self._to_row(workflow))
                return
            expected = workflow.version
            if row.version > expected:
                raise RuntimeError("workflow optimistic lock conflict")
            self._update_row(row, workflow)
            row.version += 1
            workflow.version = row.version

    async def record_step(
        self,
        workflow_id: str,
        step: str,
        provider: str,
        outcome: str,
        safe_details: Mapping[str, Any],
    ) -> None:
        async with self.database.sessions.begin() as session:
            count = len(
                (
                    await session.scalars(
                        select(WorkflowStepRow).where(
                            WorkflowStepRow.workflow_id == workflow_id,
                            WorkflowStepRow.step == step,
                        )
                    )
                ).all()
            )
            session.add(
                WorkflowStepRow(
                    workflow_id=workflow_id,
                    step=step,
                    provider=provider,
                    attempt=count + 1,
                    outcome=outcome,
                    safe_details=dict(safe_details),
                )
            )

    async def recoverable(self) -> Sequence[WorkflowEvidence]:
        terminal = {"CONFIRMED", "FAILED", "CANCELLED"}
        async with self.database.sessions() as session:
            rows = (await session.scalars(select(WorkflowRow).where(WorkflowRow.phase.not_in(terminal)))).all()
            return [self._from_row(row) for row in rows]

    async def claim(self, operation: str, subject: str, key: str, request_hash: str) -> IdempotencyDecision:
        async with self.database.sessions.begin() as session:
            row = await session.scalar(
                select(IdempotencyRow)
                .where(
                    IdempotencyRow.operation == operation,
                    IdempotencyRow.authenticated_subject == subject,
                    IdempotencyRow.idempotency_key == key,
                )
                .with_for_update()
            )
            if row:
                if row.request_hash != request_hash:
                    raise IdempotencyConflict()
                if row.response_status is not None and row.response_body is not None:
                    return IdempotencyDecision(
                        "REPLAY",
                        row.workflow_id,
                        OperationResult(row.response_status, row.response_body),
                    )
                return IdempotencyDecision("IN_PROGRESS", row.workflow_id)
            workflow_id = str(uuid4())
            session.add(
                IdempotencyRow(
                    operation=operation,
                    authenticated_subject=subject,
                    idempotency_key=key,
                    request_hash=request_hash,
                    workflow_id=workflow_id,
                )
            )
            return IdempotencyDecision("NEW", workflow_id)

    async def complete(self, operation: str, subject: str, key: str, result: OperationResult) -> None:
        async with self.database.sessions.begin() as session:
            row = await session.scalar(
                select(IdempotencyRow)
                .where(
                    IdempotencyRow.operation == operation,
                    IdempotencyRow.authenticated_subject == subject,
                    IdempotencyRow.idempotency_key == key,
                )
                .with_for_update()
            )
            if row is None:
                raise RuntimeError("idempotency record missing")
            row.response_status, row.response_body = (
                result.status_code,
                dict(result.body),
            )

    async def append(
        self,
        correlation_id: str,
        service: str,
        operation: str,
        status: str,
        duration_ms: int,
        error_code: str | None = None,
    ) -> None:
        async with self.database.sessions.begin() as session:
            session.add(
                TraceStepRow(
                    correlation_id=correlation_id,
                    service=service,
                    operation=operation,
                    status=status,
                    duration_ms=duration_ms,
                    error_code=error_code,
                )
            )

    async def list(self, correlation_id: str) -> Sequence[Mapping[str, Any]]:
        async with self.database.sessions() as session:
            rows = (
                await session.scalars(select(TraceStepRow).where(TraceStepRow.correlation_id == correlation_id).order_by(TraceStepRow.id))
            ).all()
            return [
                {
                    "service": row.service,
                    "operation": row.operation,
                    "status": row.status,
                    "durationMs": row.duration_ms,
                    "errorCode": row.error_code,
                }
                for row in rows
            ]

    async def enqueue_many(self, workflow_id: str, items: Sequence[OutboxItem]) -> None:
        async with self.database.sessions.begin() as session:
            workflow = await session.get(WorkflowRow, workflow_id, with_for_update=True)
            if workflow is None or workflow.phase != "CONFIRMED":
                raise RuntimeError("outbox requires a confirmed workflow")
            for item in items:
                session.add(
                    OutboxRow(
                        message_id=item.message_id,
                        workflow_id=workflow_id,
                        destination=item.destination,
                        message_type=item.message_type,
                        payload=dict(item.payload),
                        correlation_id=item.correlation_id,
                    )
                )

    async def commit_with_outbox(self, workflow: WorkflowEvidence, items: Sequence[OutboxItem]) -> None:
        if workflow.phase != WorkflowPhase.CONFIRMED:
            raise RuntimeError("transactional outbox requires a confirmed workflow")
        async with self.database.sessions.begin() as session:
            row = await session.get(WorkflowRow, workflow.workflow_id, with_for_update=True)
            if row is None:
                raise RuntimeError("workflow missing")
            if row.version > workflow.version:
                raise RuntimeError("workflow optimistic lock conflict")
            self._update_row(row, workflow)
            row.version += 1
            workflow.version = row.version
            for item in items:
                session.add(
                    OutboxRow(
                        message_id=item.message_id,
                        workflow_id=workflow.workflow_id,
                        destination=item.destination,
                        message_type=item.message_type,
                        payload=dict(item.payload),
                        correlation_id=item.correlation_id,
                    )
                )

    async def due_outbox(self, now: datetime, limit: int) -> Sequence[Mapping[str, Any]]:
        async with self.database.sessions() as session:
            rows = (
                await session.scalars(select(OutboxRow).where(OutboxRow.state == "PENDING", OutboxRow.next_attempt_at <= now).limit(limit))
            ).all()
            return [
                {
                    "messageId": r.message_id,
                    "destination": r.destination,
                    "type": r.message_type,
                    "payload": r.payload,
                    "correlationId": r.correlation_id,
                    "attempts": r.attempts,
                }
                for r in rows
            ]

    async def due_jobs(self, now: datetime, limit: int, lease_until: datetime | None = None) -> Sequence[Mapping[str, Any]]:
        """Claim due jobs under a row lease so replicas never share one job.

        The row lock skips whatever another worker already holds, and the claimed rows
        get a `locked_until` lease so a crashed worker's jobs become claimable again.
        """
        async with self.database.sessions.begin() as session:
            statement = (
                select(ReconciliationRow)
                .where(
                    ReconciliationRow.state == "PENDING",
                    ReconciliationRow.next_attempt_at <= now,
                    or_(
                        ReconciliationRow.locked_until.is_(None),
                        ReconciliationRow.locked_until <= now,
                    ),
                )
                .order_by(ReconciliationRow.next_attempt_at)
                .limit(limit)
            )
            if session.bind is not None and session.bind.dialect.name == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            jobs = (await session.scalars(statement)).all()
            for row in jobs:
                row.locked_until = lease_until
            return [
                {
                    "jobId": r.id,
                    "workflowId": r.workflow_id,
                    "kind": r.kind,
                    "payload": r.payload,
                    "idempotencyKey": r.idempotency_key,
                    "attempts": r.attempts,
                    "deadlineAt": r.deadline_at,
                    "extensionCount": r.extension_count,
                }
                for r in jobs
            ]

    async def delivered(self, message_id: str) -> None:
        async with self.database.sessions.begin() as session:
            row = await session.get(OutboxRow, message_id, with_for_update=True)
            if row:
                row.state = "DELIVERED"

    async def failed(self, message_id: str, next_attempt_at: datetime, error_code: str) -> None:
        async with self.database.sessions.begin() as session:
            row = await session.get(OutboxRow, message_id, with_for_update=True)
            if row:
                row.attempts += 1
                row.next_attempt_at = next_attempt_at
                row.last_error_code = error_code

    async def schedule(
        self,
        workflow_id: str,
        kind: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        deadline: datetime | None = None,
    ) -> None:
        async with self.database.sessions.begin() as session:
            existing = await session.scalar(
                select(ReconciliationRow)
                .where(
                    ReconciliationRow.workflow_id == workflow_id,
                    ReconciliationRow.kind == kind,
                    ReconciliationRow.idempotency_key == idempotency_key,
                )
                .with_for_update()
            )
            if existing is not None:
                if existing.state != "COMPLETED":
                    existing.payload = dict(payload)
                return
            session.add(
                ReconciliationRow(
                    id=str(uuid4()),
                    workflow_id=workflow_id,
                    kind=kind,
                    payload=dict(payload),
                    idempotency_key=idempotency_key,
                    deadline_at=deadline,
                )
            )

    async def complete_job(self, job_id: str) -> None:
        async with self.database.sessions.begin() as session:
            row = await session.get(ReconciliationRow, job_id, with_for_update=True)
            if row:
                row.state = "COMPLETED"
                row.locked_until = None

    async def reschedule_job(self, job_id: str, next_attempt_at: datetime, evidence: Mapping[str, Any]) -> None:
        async with self.database.sessions.begin() as session:
            row = await session.get(ReconciliationRow, job_id, with_for_update=True)
            if row:
                row.attempts += 1
                row.next_attempt_at = next_attempt_at
                row.last_evidence = dict(evidence)
                row.locked_until = None
                if "extensionCount" in evidence:
                    row.extension_count = int(str(evidence["extensionCount"]))

    async def abandon_job(self, job_id: str, evidence: Mapping[str, Any]) -> None:
        async with self.database.sessions.begin() as session:
            row = await session.get(ReconciliationRow, job_id, with_for_update=True)
            if row:
                row.state = "ABANDONED"
                row.locked_until = None
                row.last_evidence = dict(evidence)

    @staticmethod
    def _to_row(value: WorkflowEvidence) -> WorkflowRow:
        row = WorkflowRow(
            id=value.workflow_id,
            public_operation=value.operation,
            authenticated_subject=value.subject,
            request_hash=value.request_hash,
            correlation_id=value.correlation_id,
            phase=value.phase.value,
        )
        SqlRepositories._update_row(row, value)
        return row

    @staticmethod
    def _update_row(row: WorkflowRow, value: WorkflowEvidence) -> None:
        row.phase = value.phase.value
        row.booking_id = value.booking_id
        row.customer_id = value.customer_id
        row.reservation_id = value.reservation_id
        row.reservation_version = value.reservation_version
        row.payment_id = value.payment_id
        row.payment_status = value.payment_status.value if value.payment_status else None
        row.ticket_ids = list(value.ticket_ids)
        row.total = value.total.as_wire() if value.total else None
        row.evidence = dict(value.evidence)

    @staticmethod
    def _from_row(row: WorkflowRow) -> WorkflowEvidence:
        total = Money(int(row.total["amountMinor"]), str(row.total["currency"])) if row.total else None
        return WorkflowEvidence(
            row.id,
            row.public_operation,
            row.authenticated_subject,
            row.request_hash,
            row.correlation_id,
            WorkflowPhase(row.phase),
            row.booking_id,
            row.customer_id,
            row.reservation_id,
            row.reservation_version,
            row.payment_id,
            PaymentOutcome(row.payment_status) if row.payment_status else None,
            list(row.ticket_ids or []),
            total,
            dict(row.evidence or {}),
            row.version,
        )
