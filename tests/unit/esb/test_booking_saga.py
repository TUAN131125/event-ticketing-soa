from __future__ import annotations

import pytest
from app.application.booking import BookingSaga
from app.application.cancellation import CancellationSaga
from app.domain.errors import (
    AmbiguousOutcome,
    BusinessFault,
    DependencyFailure,
    IdempotencyConflict,
)
from app.domain.models import PlaceBookingCommand, WorkflowPhase
from app.persistence.memory import InMemoryRepositories
from app.workers.reconciliation import ReconciliationWorker
from fakes import FakeClock, FakeProviders, request_context


def build_booking(providers: FakeProviders | None = None, reserve_attempts: int = 2):
    providers = providers or FakeProviders()
    repositories = InMemoryRepositories()
    saga = BookingSaga(
        providers,
        providers,
        providers,
        providers,
        providers,
        providers,
        repositories,
        repositories,
        repositories,
        repositories,
        repositories,
        FakeClock(),
        reserve_attempts,
    )
    command = PlaceBookingCommand(
        "UNTRUSTED-CUSTOMER", "EVT-1", ("SEAT-1",), "payment-method", "idem-key-0001"
    )
    return saga, providers, repositories, command


def call_names(providers: FakeProviders) -> list[str]:
    return [name for name, _ in providers.calls]


@pytest.mark.asyncio
async def test_booking_success_uses_authoritative_data_and_canonical_order() -> None:
    saga, providers, repositories, command = build_booking()
    result = await saga.execute(command, request_context())

    assert result.status_code == 201
    assert result.body["status"] == "CONFIRMED"
    names = call_names(providers)
    required = [
        "resolveIdentityMapping",
        "getCustomer",
        "getEvent",
        "getSaleEligibility",
        "CheckAvailability",
        "createBooking",
        "ReserveSeats",
        "bookingReservation",
        "createPayment",
        "bookingPaymentStarted",
        "authorizePayment",
        "capturePayment",
        "bookingPaymentResult",
        "issueTickets",
        "bookingTickets",
        "ConfirmSeats",
        "bookingConfirm",
    ]
    assert [names.index(name) for name in required] == sorted(
        names.index(name) for name in required
    )
    create_payload = next(
        details["payload"]
        for name, details in providers.calls
        if name == "createBooking"
    )
    assert create_payload["customerId"] == "CUS-1"
    reserve_payload = next(
        details["payload"]
        for name, details in providers.calls
        if name == "ReserveSeats"
    )
    assert reserve_payload["bookingId"] == "BK-1"
    assert len(repositories.outbox) == 2
    assert {item["destination"] for item in repositories.outbox.values()} == {
        "notification",
        "realtime",
    }


@pytest.mark.asyncio
async def test_reserve_timeout_replays_same_key_and_payload_without_get_reservation() -> (
    None
):
    providers = FakeProviders()
    providers.reserve_outcomes = [
        AmbiguousOutcome("ReserveSeats"),
        {
            "reservationId": "RES-1",
            "resourceVersion": 1,
            "expiresAt": "2026-08-05T10:10:00Z",
        },
    ]
    saga, providers, _, command = build_booking(providers)
    result = await saga.execute(command, request_context())

    assert result.status_code == 201
    calls = [details for name, details in providers.calls if name == "ReserveSeats"]
    assert len(calls) == 2
    assert calls[0]["idempotencyKey"] == calls[1]["idempotencyKey"]
    assert calls[0]["payload"] == calls[1]["payload"]
    assert "GetReservation" not in call_names(providers)


@pytest.mark.asyncio
async def test_reserve_unknown_stays_pending_and_schedules_same_key_reconciliation() -> (
    None
):
    providers = FakeProviders()
    providers.reserve_outcomes = [AmbiguousOutcome("ReserveSeats")]
    saga, providers, repositories, command = build_booking(providers)
    result = await saga.execute(command, request_context())

    assert result.status_code == 202
    assert result.body["status"] == "PENDING"
    assert len([name for name in call_names(providers) if name == "ReserveSeats"]) == 2
    assert "GetReservation" not in call_names(providers)
    assert not (
        {"createPayment", "issueTickets", "ConfirmSeats", "ReleaseSeats"}
        & set(call_names(providers))
    )
    job = next(iter(repositories.jobs.values()))
    reserve_call = next(
        details for name, details in providers.calls if name == "ReserveSeats"
    )
    assert job["kind"] == "RESERVE_REPLAY"
    assert job["idempotencyKey"] == reserve_call["idempotencyKey"]
    assert job["payload"]["request"] == reserve_call["payload"]


@pytest.mark.asyncio
async def test_reserve_determined_failure_fails_booking_without_release_or_payment() -> (
    None
):
    providers = FakeProviders()
    providers.reserve_outcomes = [
        BusinessFault("SEAT_UNAVAILABLE", "Seat unavailable.", 409, False)
    ]
    saga, providers, _, command = build_booking(providers)
    with pytest.raises(BusinessFault):
        await saga.execute(command, request_context())
    names = call_names(providers)
    assert "bookingFail" in names
    assert not ({"ReleaseSeats", "createPayment", "issueTickets"} & set(names))


@pytest.mark.asyncio
async def test_booking_reservation_evidence_failure_releases_then_fails() -> None:
    providers = FakeProviders()
    providers.transition_failures.add("bookingReservation")
    saga, providers, _, command = build_booking(providers)
    with pytest.raises(DependencyFailure):
        await saga.execute(command, request_context())
    names = call_names(providers)
    assert (
        names.index("bookingReservation")
        < names.index("ReleaseSeats")
        < names.index("bookingFail")
    )


@pytest.mark.asyncio
async def test_payment_failed_releases_seat_and_never_issues_ticket() -> None:
    providers = FakeProviders()
    providers.payment_outcomes["authorizePayment"] = {"status": "FAILED"}
    saga, providers, repositories, command = build_booking(providers)
    result = await saga.execute(command, request_context())
    assert result.status_code == 402
    assert "ReleaseSeats" in call_names(providers)
    assert "issueTickets" not in call_names(providers)
    assert next(iter(repositories.workflows.values())).phase == WorkflowPhase.FAILED


@pytest.mark.asyncio
async def test_declined_payment_business_fault_still_releases_and_fails_the_booking() -> (
    None
):
    """Payment Service signals a decline with a 402 fault, not a FAILED status body."""
    providers = FakeProviders()
    providers.payment_outcomes["authorizePayment"] = BusinessFault(
        "PAYMENT_DECLINED", "Payment was declined.", 402, False
    )
    saga, providers, repositories, command = build_booking(providers)
    result = await saga.execute(command, request_context())
    names = call_names(providers)
    assert result.status_code == 402
    assert names.index("ReleaseSeats") < names.index("bookingFail")
    assert "issueTickets" not in names
    assert "ConfirmSeats" not in names
    assert next(iter(repositories.workflows.values())).phase == WorkflowPhase.FAILED


@pytest.mark.asyncio
async def test_payment_unknown_has_no_unsafe_compensation_and_schedules_reconciliation() -> (
    None
):
    providers = FakeProviders()
    providers.payment_outcomes["capturePayment"] = AmbiguousOutcome("capturePayment")
    saga, providers, repositories, command = build_booking(providers)
    result = await saga.execute(command, request_context())
    names = call_names(providers)
    assert result.status_code == 202
    assert result.body["status"] == "PAYMENT_PROCESSING"
    assert not (
        {"ReleaseSeats", "issueTickets", "ConfirmSeats", "bookingConfirm"} & set(names)
    )
    assert {job["kind"] for job in repositories.jobs.values()} == {"PAYMENT_UNKNOWN"}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["ticket", "seat", "booking"])
async def test_failure_after_capture_is_compensation_pending(failure: str) -> None:
    providers = FakeProviders()
    if failure == "ticket":
        providers.ticket_failure = True
    elif failure == "seat":
        providers.confirm_failure = True
    else:
        providers.transition_failures.add("bookingConfirm")
    saga, providers, repositories, command = build_booking(providers)
    with pytest.raises(DependencyFailure) as raised:
        await saga.execute(command, request_context())
    assert raised.value.code == "AFTER_CAPTURE_FAILURE"
    workflow = next(iter(repositories.workflows.values()))
    assert workflow.payment_status.value == "CAPTURED"
    assert workflow.phase == WorkflowPhase.COMPENSATION_PENDING
    assert {job["kind"] for job in repositories.jobs.values()} == {
        "AFTER_CAPTURE_COMPENSATION"
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("mapping", "IDENTITY_NOT_MAPPED"),
        ("inactive", "CUSTOMER_INACTIVE"),
        ("event", "EVENT_NOT_ON_SALE"),
        ("seat", "SEAT_UNAVAILABLE"),
    ],
)
async def test_pre_payment_fail_closed(mutation: str, code: str) -> None:
    providers = FakeProviders()
    if mutation == "mapping":
        providers.mapping = {"status": "NOT_FOUND"}
    if mutation == "inactive":
        providers.customer = {"customerId": "CUS-1", "status": "INACTIVE"}
    if mutation == "event":
        providers.eligibility = {"eligible": False}
    if mutation == "seat":
        providers.available = False
    saga, providers, _, command = build_booking(providers)
    with pytest.raises(BusinessFault) as raised:
        await saga.execute(command, request_context())
    assert raised.value.code == code
    assert "createPayment" not in call_names(providers)


@pytest.mark.asyncio
async def test_idempotency_replay_and_different_payload_conflict() -> None:
    saga, providers, _, command = build_booking()
    first = await saga.execute(command, request_context())
    calls_after_first = len(providers.calls)
    second = await saga.execute(command, request_context())
    assert second == first
    assert len(providers.calls) == calls_after_first
    changed = PlaceBookingCommand(
        "UNTRUSTED-CUSTOMER",
        "EVT-1",
        ("SEAT-2",),
        "payment-method",
        command.idempotency_key,
    )
    with pytest.raises(IdempotencyConflict):
        await saga.execute(changed, request_context())


@pytest.mark.asyncio
async def test_cancellation_is_access_and_evidence_driven() -> None:
    providers = FakeProviders()
    repositories = InMemoryRepositories()
    saga = CancellationSaga(
        providers,
        providers,
        providers,
        providers,
        repositories,
        repositories,
        repositories,
        FakeClock(),
    )
    result = await saga.execute("BK-1", "cancel-key-001", request_context())
    names = call_names(providers)
    assert result.body["status"] == "CANCELLED"
    assert names.index("bookingAccessDecision") < names.index("getBooking")
    assert (
        names.index("getBooking")
        < names.index("cancelTicket")
        < names.index("createRefund")
        < names.index("GetReservation")
        < names.index("ReleaseSeats")
        < names.index("bookingCancel")
    )


@pytest.mark.asyncio
async def test_partial_cancellation_compensation_is_not_reported_cancelled() -> None:
    providers = FakeProviders()
    providers.release_failure = True
    repositories = InMemoryRepositories()
    saga = CancellationSaga(
        providers,
        providers,
        providers,
        providers,
        repositories,
        repositories,
        repositories,
        FakeClock(),
    )
    result = await saga.execute("BK-1", "cancel-key-002", request_context())
    assert result.body["status"] == "COMPENSATION_PENDING"
    transition = next(
        details for name, details in providers.calls if name == "bookingCancel"
    )
    assert transition["payload"]["compensationStatus"] == "PENDING"
    assert {job["kind"] for job in repositories.jobs.values()} == {
        "CANCEL_COMPENSATION"
    }
    providers.release_failure = False
    worker = ReconciliationWorker(
        repositories,
        repositories,
        providers,
        providers,
        providers,
        providers,
        repositories,
        FakeClock(),
    )
    assert await worker.run_once() == 1
    assert next(iter(repositories.workflows.values())).phase == WorkflowPhase.CANCELLED
    assert not repositories.jobs
