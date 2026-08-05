from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.domain.errors import IdempotencyConflict
from app.domain.models import (
    IdempotencyDecision,
    OperationResult,
    OutboxItem,
    WorkflowEvidence,
)


class InMemoryRepositories:
    """Controlled test double only; production composition uses SQL repositories."""

    def __init__(self) -> None:
        self.workflows: dict[str, WorkflowEvidence] = {}
        self.steps: list[dict[str, Any]] = []
        self.abandoned: dict[str, dict[str, Any]] = {}
        self.idempotency: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.traces: list[dict[str, Any]] = []
        self.outbox: dict[str, dict[str, Any]] = {}
        self.jobs: dict[str, dict[str, Any]] = {}

    async def create(self, workflow: WorkflowEvidence) -> None:
        self.workflows.setdefault(workflow.workflow_id, workflow)

    async def get(self, workflow_id: str) -> WorkflowEvidence | None:
        return self.workflows.get(workflow_id)

    async def save(self, workflow: WorkflowEvidence) -> None:
        workflow.version += 1
        self.workflows[workflow.workflow_id] = workflow

    async def record_step(
        self,
        workflow_id: str,
        step: str,
        provider: str,
        outcome: str,
        safe_details: Mapping[str, Any],
    ) -> None:
        self.steps.append(
            {
                "workflowId": workflow_id,
                "step": step,
                "provider": provider,
                "outcome": outcome,
                "details": dict(safe_details),
            }
        )

    async def recoverable(self) -> Sequence[WorkflowEvidence]:
        return [w for w in self.workflows.values() if w.phase.value not in {"CONFIRMED", "FAILED", "CANCELLED"}]

    async def claim(self, operation: str, subject: str, key: str, request_hash: str) -> IdempotencyDecision:
        scope = (operation, subject, key)
        record = self.idempotency.get(scope)
        if record:
            if record["hash"] != request_hash:
                raise IdempotencyConflict()
            if record.get("result"):
                return IdempotencyDecision("REPLAY", record["workflowId"], record["result"])
            return IdempotencyDecision("IN_PROGRESS", record["workflowId"])
        workflow_id = str(uuid4())
        self.idempotency[scope] = {"hash": request_hash, "workflowId": workflow_id}
        return IdempotencyDecision("NEW", workflow_id)

    async def complete(self, operation: str, subject: str, key: str, result: OperationResult) -> None:
        self.idempotency[(operation, subject, key)]["result"] = result

    async def append(
        self,
        correlation_id: str,
        service: str,
        operation: str,
        status: str,
        duration_ms: int,
        error_code: str | None = None,
    ) -> None:
        self.traces.append(
            {
                "correlationId": correlation_id,
                "service": service,
                "operation": operation,
                "status": status,
                "durationMs": duration_ms,
                "errorCode": error_code,
            }
        )

    async def list(self, correlation_id: str) -> Sequence[Mapping[str, Any]]:
        return [{k: v for k, v in row.items() if k != "correlationId"} for row in self.traces if row["correlationId"] == correlation_id]

    async def enqueue_many(self, workflow_id: str, items: Sequence[OutboxItem]) -> None:
        for item in items:
            self.outbox[item.message_id] = {
                "messageId": item.message_id,
                "workflowId": workflow_id,
                "destination": item.destination,
                "type": item.message_type,
                "payload": dict(item.payload),
                "correlationId": item.correlation_id,
                "attempts": 0,
                "state": "PENDING",
            }

    async def commit_with_outbox(self, workflow: WorkflowEvidence, items: Sequence[OutboxItem]) -> None:
        await self.save(workflow)
        await self.enqueue_many(workflow.workflow_id, items)

    async def due_outbox(self, now: datetime, limit: int) -> Sequence[Mapping[str, Any]]:
        return [item for item in self.outbox.values() if item["state"] == "PENDING"][:limit]

    async def due_jobs(self, now: datetime, limit: int, lease_until: datetime | None = None) -> Sequence[Mapping[str, Any]]:
        return list(self.jobs.values())[:limit]

    async def delivered(self, message_id: str) -> None:
        self.outbox[message_id]["state"] = "DELIVERED"

    async def failed(self, message_id: str, next_attempt_at: datetime, error_code: str) -> None:
        self.outbox[message_id].update(
            attempts=self.outbox[message_id]["attempts"] + 1,
            nextAttemptAt=next_attempt_at,
            lastErrorCode=error_code,
        )

    async def schedule(
        self,
        workflow_id: str,
        kind: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        deadline: datetime | None = None,
    ) -> None:
        for job in self.jobs.values():
            if job["workflowId"] == workflow_id and job["kind"] == kind and job["idempotencyKey"] == idempotency_key:
                job["payload"] = dict(payload)
                return
        job_id = str(uuid4())
        self.jobs[job_id] = {
            "jobId": job_id,
            "workflowId": workflow_id,
            "kind": kind,
            "payload": dict(payload),
            "idempotencyKey": idempotency_key,
            "attempts": 0,
            "deadlineAt": deadline,
            "extensionCount": 0,
        }

    async def complete_job(self, job_id: str) -> None:
        self.jobs.pop(job_id, None)

    async def reschedule_job(self, job_id: str, next_attempt_at: datetime, evidence: Mapping[str, Any]) -> None:
        self.jobs[job_id].update(
            nextAttemptAt=next_attempt_at,
            evidence=dict(evidence),
            attempts=self.jobs[job_id]["attempts"] + 1,
        )
        if "extensionCount" in evidence:
            self.jobs[job_id]["extensionCount"] = int(str(evidence["extensionCount"]))

    async def abandon_job(self, job_id: str, evidence: Mapping[str, Any]) -> None:
        job = self.jobs.pop(job_id, None)
        if job is not None:
            self.abandoned[job_id] = {**job, "evidence": dict(evidence)}
