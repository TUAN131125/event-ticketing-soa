import time

import pytest

from app.domain.models import Principal, RequestContext, Workflow, WorkflowStatus
from app.persistence.repositories import InMemoryRepository
from app.workers.reconciliation import ReconciliationWorker


class Saga:
    def __init__(self):
        self.compensated = []
        self.reconciled = []

    async def compensate(self, workflow_id, context):
        self.compensated.append(workflow_id)
        return 200, {}

    async def reconcile(self, workflow_id, context):
        self.reconciled.append(workflow_id)
        return 200, {}


@pytest.mark.asyncio
async def test_reconciliation_worker_routes_compensation_pending_to_compensator():
    repository = InMemoryRepository()
    workflow = Workflow(
        workflow_id="wf-comp",
        idempotency_key="idem-comp",
        request_hash="hash",
        customer_id="cust-1",
        event_id="event-1",
        seat_ids=["A1"],
        status=WorkflowStatus.COMPENSATION_PENDING,
        evidence={"correlationId": "corr", "traceId": "1" * 32},
    )
    await repository.save(workflow)
    saga = Saga()
    worker = ReconciliationWorker(repository, saga, batch_size=10)

    assert await worker.run_once() == 1
    assert saga.compensated == ["wf-comp"]
    assert saga.reconciled == []
