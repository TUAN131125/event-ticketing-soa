from __future__ import annotations

import asyncio
import time

from app.domain.models import Principal, RequestContext, WorkflowStatus

RECONCILABLE_STATUSES = (
    WorkflowStatus.PAYMENT_UNKNOWN,
    WorkflowStatus.PAYMENT_PROCESSING,
    WorkflowStatus.SEAT_CONFIRMED,
    WorkflowStatus.TICKETS_ISSUED,
    WorkflowStatus.COMPENSATION_PENDING,
)


class ReconciliationWorker:
    """Resumes persisted workflows without inventing provider outcomes."""

    def __init__(
        self,
        workflows,
        saga,
        interval_seconds: float = 2.0,
        batch_size: int = 50,
        operation_timeout_seconds: float = 20.0,
    ) -> None:
        self.workflows = workflows
        self.saga = saga
        self.interval_seconds = interval_seconds
        self.batch_size = batch_size
        self.operation_timeout_seconds = operation_timeout_seconds

    async def run_once(self) -> int:
        pending = []
        seen: set[str] = set()
        for status in RECONCILABLE_STATUSES:
            rows = await self.workflows.list_by_status(
                status.value,
                self.batch_size,
            )
            for workflow in rows:
                if workflow.workflow_id not in seen:
                    pending.append(workflow)
                    seen.add(workflow.workflow_id)
                if len(pending) >= self.batch_size:
                    break
            if len(pending) >= self.batch_size:
                break

        processed = 0
        for workflow in pending:
            context = RequestContext(
                correlation_id=str(
                    workflow.evidence.get("correlationId", workflow.workflow_id)
                ),
                trace_id=str(workflow.evidence.get("traceId", "0" * 32)),
                deadline_monotonic=time.monotonic()
                + self.operation_timeout_seconds,
                principal=Principal(
                    "esb-reconciliation",
                    frozenset({"SYSTEM"}),
                    workflow.customer_id,
                ),
            )
            try:
                if workflow.status == WorkflowStatus.COMPENSATION_PENDING:
                    await self.saga.compensate(workflow.workflow_id, context)
                else:
                    await self.saga.reconcile(workflow.workflow_id, context)
            except Exception as exc:
                workflow.evidence["lastReconciliationErrorCode"] = getattr(
                    exc,
                    "code",
                    type(exc).__name__.upper(),
                )
                await self.workflows.save(workflow)
            processed += 1
        return processed

    async def run_forever(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                continue
