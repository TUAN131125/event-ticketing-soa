"""Reconciliation of an unknown payment: settle, refund, back off or abandon."""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.domain.models import PaymentOutcome, WorkflowPhase
from app.workers.reconciliation import ReconciliationWorker
from fakes import FakeClock, FakeProviders, request_context
from test_booking_saga import build_booking, call_names


def worker(
    providers: FakeProviders, repositories, clock: FakeClock
) -> ReconciliationWorker:
    return ReconciliationWorker(
        repositories,
        repositories,
        providers,
        providers,
        providers,
        providers,
        repositories,
        clock,
        backoff_seconds=15,
        max_backoff_seconds=300,
        lease_seconds=60,
    )


async def unknown_payment_workflow(providers: FakeProviders):
    """Drive the saga into the UNKNOWN state the reconciliation worker picks up."""
    from app.domain.errors import AmbiguousOutcome

    providers.payment_outcomes["authorizePayment"] = AmbiguousOutcome(
        "authorizePayment"
    )
    saga, providers, repositories, command = build_booking(providers)
    result = await saga.execute(command, request_context())
    assert result.status_code == 202
    providers.calls.clear()
    return providers, repositories


@pytest.mark.asyncio
async def test_worker_confirms_when_payment_turns_out_captured() -> None:
    providers, repositories = await unknown_payment_workflow(FakeProviders())
    providers.payment_outcomes["reconcilePayment"] = {"status": "CAPTURED"}

    processed = await worker(providers, repositories, FakeClock()).run_once()
    names = call_names(providers)

    assert processed == 1
    assert "GetReservation" in names, "the seat must be verified before confirming"
    assert names.count("issueTickets") == 1, "tickets are issued exactly once"
    assert "ConfirmSeats" in names
    assert "ReleaseSeats" not in names
    assert next(iter(repositories.workflows.values())).phase is WorkflowPhase.CONFIRMED
    assert not repositories.jobs, "a settled reconciliation is completed"


@pytest.mark.asyncio
async def test_worker_releases_when_payment_turns_out_declined() -> None:
    providers, repositories = await unknown_payment_workflow(FakeProviders())
    providers.payment_outcomes["reconcilePayment"] = {"status": "DECLINED"}

    await worker(providers, repositories, FakeClock()).run_once()
    names = call_names(providers)

    assert "ReleaseSeats" in names
    assert "issueTickets" not in names
    assert "ConfirmSeats" not in names
    assert next(iter(repositories.workflows.values())).phase is WorkflowPhase.FAILED
    assert not repositories.jobs


@pytest.mark.asyncio
async def test_captured_payment_without_a_seat_refunds_instead_of_confirming() -> None:
    providers, repositories = await unknown_payment_workflow(FakeProviders())
    providers.payment_outcomes["reconcilePayment"] = {"status": "CAPTURED"}
    providers.reservation_status = "EXPIRED"

    await worker(providers, repositories, FakeClock()).run_once()
    names = call_names(providers)

    assert "createRefund" in names, "captured money must be refunded"
    assert "issueTickets" not in names
    assert "ConfirmSeats" not in names
    workflow = next(iter(repositories.workflows.values()))
    assert workflow.phase is not WorkflowPhase.CONFIRMED


@pytest.mark.asyncio
async def test_still_unknown_payment_backs_off_without_touching_seat_or_ticket() -> (
    None
):
    providers, repositories = await unknown_payment_workflow(FakeProviders())
    providers.payment_outcomes["reconcilePayment"] = {"status": "UNKNOWN"}
    clock = FakeClock()

    await worker(providers, repositories, clock).run_once()
    names = call_names(providers)

    assert "ReleaseSeats" not in names, (
        "an unknown payment must never be assumed failed"
    )
    assert "issueTickets" not in names
    job = next(iter(repositories.jobs.values()))
    assert job["attempts"] == 1
    assert job["nextAttemptAt"] > clock.now()


@pytest.mark.asyncio
async def test_reconciliation_stops_at_the_deadline_without_inventing_an_outcome() -> (
    None
):
    providers, repositories = await unknown_payment_workflow(FakeProviders())
    providers.payment_outcomes["reconcilePayment"] = {"status": "UNKNOWN"}
    clock = FakeClock()
    job_id, job = next(iter(repositories.jobs.items()))
    job["deadlineAt"] = clock.now() - timedelta(seconds=1)

    await worker(providers, repositories, clock).run_once()
    names = call_names(providers)

    assert job_id in repositories.abandoned
    assert repositories.abandoned[job_id]["evidence"]["outcome"] == "DEADLINE_EXCEEDED"
    assert "ReleaseSeats" not in names, "the deadline must not fabricate a failure"
    assert "createRefund" not in names
    workflow = next(iter(repositories.workflows.values()))
    assert workflow.payment_status is PaymentOutcome.UNKNOWN


@pytest.mark.asyncio
async def test_worker_replay_never_doubles_a_side_effect() -> None:
    providers, repositories = await unknown_payment_workflow(FakeProviders())
    providers.payment_outcomes["reconcilePayment"] = {"status": "CAPTURED"}
    engine = worker(providers, repositories, FakeClock())

    await engine.run_once()
    first_pass = call_names(providers)
    # A restarted worker re-scans; the completed job must not run a second time.
    await engine.run_once()
    second_pass = call_names(providers)

    assert first_pass.count("issueTickets") == 1
    assert second_pass.count("issueTickets") == 1, "no duplicate ticket issue"
    assert second_pass.count("ConfirmSeats") == 1
    assert second_pass.count("reconcilePayment") == 1, "no duplicate payment command"


@pytest.mark.asyncio
async def test_a_crash_before_completion_replays_with_the_same_provider_keys() -> None:
    """A restart mid-job must reuse every key, so providers deduplicate the replay."""
    providers, repositories = await unknown_payment_workflow(FakeProviders())
    providers.payment_outcomes["reconcilePayment"] = {"status": "CAPTURED"}
    engine = worker(providers, repositories, FakeClock())

    # Snapshot the queued job so it can be restored as a crashed worker would leave it.
    job_id, original = next(iter(repositories.jobs.items()))
    snapshot = dict(original)

    await engine.run_once()
    first = _keys_by_operation(providers)

    providers.calls.clear()
    repositories.jobs[job_id] = snapshot
    await engine.run_once()
    second = _keys_by_operation(providers)

    for operation in ("issueTickets", "ConfirmSeats", "reconcilePayment"):
        assert first[operation] == second[operation], (
            f"{operation} must replay under its original idempotency key"
        )


def _keys_by_operation(providers: FakeProviders) -> dict[str, str]:
    keys: dict[str, str] = {}
    for name, payload in providers.calls:
        if "idempotencyKey" in payload:
            keys.setdefault(name, str(payload["idempotencyKey"]))
    return keys


@pytest.mark.asyncio
async def test_worker_uses_a_stable_idempotency_key_across_retries() -> None:
    providers, repositories = await unknown_payment_workflow(FakeProviders())
    providers.payment_outcomes["reconcilePayment"] = {"status": "UNKNOWN"}
    engine = worker(providers, repositories, FakeClock())

    await engine.run_once()
    await engine.run_once()

    keys = [
        payload["idempotencyKey"]
        for name, payload in providers.calls
        if name == "reconcilePayment"
    ]
    assert len(keys) == 2
    assert keys[0] == keys[1], "a retry must reuse the original idempotency key"
