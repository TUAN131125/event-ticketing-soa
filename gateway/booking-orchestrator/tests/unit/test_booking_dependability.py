import time
from types import SimpleNamespace

import pytest

from app.application.booking import BookingSaga
from app.domain.errors import Conflict
from app.domain.models import Principal, RequestContext
from app.persistence.repositories import InMemoryRepository
from tests.fakes import Booking, Customer, Event, Payment, Seat, Ticket


def context():
    return RequestContext(
        "corr", "1" * 32, time.monotonic() + 5,
        Principal("user", frozenset({"CUSTOMER"}), "cust-1"),
    )


def saga(log, payment_status="CAPTURED", ttl=321):
    repository = InMemoryRepository()
    booking = Booking(log)
    seat = Seat(log)
    payment = Payment(log, payment_status)
    service = BookingSaga(
        Customer(), Event(), seat, booking, payment, Ticket(log),
        repository, repository, SimpleNamespace(reservation_ttl_seconds=ttl),
    )
    return service, repository, booking, seat, payment


@pytest.mark.asyncio
async def test_authoritative_seat_type_mapping_and_configured_ttl():
    log = []
    service, _, booking, seat, _ = saga(log, ttl=777)
    status, _ = await service.place(
        {"eventId": "e1", "seatIds": ["A1", "V1"], "paymentMethodToken": "success"},
        "idem-authoritative", context(),
    )
    assert status == 201
    assert seat.last_ttl == 777
    assert booking.last_create["items"] == [
        {"seatId": "A1", "ticketType": "STD", "unitPrice": 100, "priceCurrency": "VND"},
        {"seatId": "V1", "ticketType": "VIP", "unitPrice": 200, "priceCurrency": "VND"},
    ]


@pytest.mark.asyncio
async def test_idempotent_replay_returns_frozen_response_without_new_side_effects():
    log = []
    service, _, _, _, _ = saga(log)
    request = {"eventId": "e1", "seatIds": ["A1"], "paymentMethodToken": "success"}
    first = await service.place(request, "idem-replay", context())
    count = len(log)
    second = await service.place(request, "idem-replay", context())
    assert first == second
    assert len(log) == count


@pytest.mark.asyncio
async def test_reused_key_with_changed_request_is_rejected():
    log = []
    service, _, _, _, _ = saga(log)
    await service.place(
        {"eventId": "e1", "seatIds": ["A1"], "paymentMethodToken": "success"},
        "idem-conflict", context(),
    )
    with pytest.raises(Conflict) as exc:
        await service.place(
            {"eventId": "e1", "seatIds": ["V1"], "paymentMethodToken": "success"},
            "idem-conflict", context(),
        )
    assert exc.value.code == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.asyncio
async def test_confirm_seat_failure_never_issues_ticket():
    class FailingSeat(Seat):
        async def confirm(self, *args):
            self.log.append("confirm-seat-failed")
            raise RuntimeError("seat confirmation failed")

    log = []
    repository = InMemoryRepository()
    service = BookingSaga(
        Customer(), Event(), FailingSeat(log), Booking(log), Payment(log), Ticket(log),
        repository, repository, SimpleNamespace(reservation_ttl_seconds=60),
    )
    with pytest.raises(RuntimeError):
        await service.place(
            {"eventId": "e1", "seatIds": ["A1"], "paymentMethodToken": "success"},
            "idem-seat-fail", context(),
        )
    assert "issue-ticket" not in log


@pytest.mark.asyncio
async def test_payment_decline_returns_contract_error_and_releases_seat():
    class DeclinedPayment(Payment):
        async def authorize(self, *args):
            self.log.append("authorize")
            return {"status": "FAILED", "failureCode": "PAYMENT_DECLINED", "resourceVersion": 2}

    log = []
    repository = InMemoryRepository()
    service = BookingSaga(
        Customer(), Event(), Seat(log), Booking(log), DeclinedPayment(log), Ticket(log),
        repository, repository, SimpleNamespace(reservation_ttl_seconds=60),
    )
    status, body = await service.place(
        {"eventId": "e1", "seatIds": ["A1"], "paymentMethodToken": "decline"},
        "idem-decline", context(),
    )
    assert status == 402
    assert body["error"]["code"] == "PAYMENT_DECLINED"
    assert log.index("release-seat") < log.index("booking-fail")
    assert "issue-ticket" not in log


@pytest.mark.asyncio
async def test_unknown_payment_can_resume_from_persisted_evidence():
    log = []
    service, repository, _, _, payment = saga(log, payment_status="UNKNOWN")
    status, body = await service.place(
        {"eventId": "e1", "seatIds": ["A1"], "paymentMethodToken": "timeout"},
        "idem-unknown", context(),
    )
    assert status == 202
    payment.status = "CAPTURED"
    workflow = await repository.get(body["workflowId"])
    reconciled_status, reconciled = await service.reconcile(workflow.workflow_id, context())
    assert reconciled_status == 201
    assert reconciled["status"] == "CONFIRMED"
    assert log.index("confirm-seat") < log.index("issue-ticket")


@pytest.mark.asyncio
async def test_post_capture_ticket_failure_is_persisted_and_compensated():
    class FailingTicket(Ticket):
        async def issue(self, *args):
            self.log.append("issue-ticket-failed")
            raise RuntimeError("ticket service unavailable")

    log = []
    repository = InMemoryRepository()
    booking = Booking(log)
    payment = Payment(log)
    service = BookingSaga(
        Customer(),
        Event(),
        Seat(log),
        booking,
        payment,
        FailingTicket(log),
        repository,
        repository,
        SimpleNamespace(reservation_ttl_seconds=60),
    )

    with pytest.raises(RuntimeError):
        await service.place(
            {
                "eventId": "e1",
                "seatIds": ["A1"],
                "paymentMethodToken": "tok_success_compensation",
            },
            "idem-post-capture-failure",
            context(),
        )

    workflow = next(iter(repository.workflows.values()))
    assert workflow.status.value == "COMPENSATION_PENDING"
    assert "booking-fail" in log

    status, body = await service.compensate(workflow.workflow_id, context())
    assert status == 409
    assert body["error"]["code"] == "BOOKING_WORKFLOW_FAILED"
    assert "refund" in log
    assert "release-seat" in log
    assert log[-1] == "booking-comp-result"

@pytest.mark.asyncio
async def test_clear_seat_unavailability_fails_provisional_booking() -> None:
    class UnavailableSeat(Seat):
        async def check_availability(self, event_id, seat_references, ctx):
            return {"available": False, "unavailableSeatId": "A1"}

    log: list[str] = []
    repository = InMemoryRepository()
    booking = Booking(log)
    service = BookingSaga(
        Customer(),
        Event(),
        UnavailableSeat(log),
        booking,
        Payment(log),
        Ticket(log),
        repository,
        repository,
        SimpleNamespace(reservation_ttl_seconds=60),
    )

    with pytest.raises(Conflict) as exc:
        await service.place(
            {
                "eventId": "e1",
                "seatIds": ["A1"],
                "paymentMethodToken": "tok-seat-unavailable",
            },
            "idem-seat-unavailable",
            context(),
        )

    assert exc.value.code == "SEAT_UNAVAILABLE"
    assert "booking-fail" in log
    assert "payment-create" not in log
    workflow = next(iter(repository.workflows.values()))
    assert workflow.status.value == "FAILED"


@pytest.mark.asyncio
async def test_retryable_capture_error_becomes_payment_unknown_and_updates_booking() -> None:
    from app.domain.errors import DependencyError

    class AmbiguousPayment(Payment):
        async def capture(self, *args):
            self.log.append("capture-timeout")
            raise DependencyError(
                "DEPENDENCY_TIMEOUT",
                "payment capture timed out",
                504,
                True,
            )

    log: list[str] = []
    repository = InMemoryRepository()
    booking = Booking(log)
    service = BookingSaga(
        Customer(),
        Event(),
        Seat(log),
        booking,
        AmbiguousPayment(log),
        Ticket(log),
        repository,
        repository,
        SimpleNamespace(reservation_ttl_seconds=60),
    )

    status, body = await service.place(
        {
            "eventId": "e1",
            "seatIds": ["A1"],
            "paymentMethodToken": "tok-capture-timeout",
        },
        "idem-capture-timeout",
        context(),
    )

    assert status == 202
    assert body["paymentStatus"] == "UNKNOWN"
    assert booking.payloads["payment-result"]["paymentStatus"] == "UNKNOWN"
    assert "confirm-seat" not in log
    assert "issue-ticket" not in log

@pytest.mark.asyncio
async def test_reconciliation_resumes_after_seat_confirmation_without_reconfirming() -> None:
    from app.domain.models import PaymentStatus, Workflow, WorkflowStatus

    log: list[str] = []
    repository = InMemoryRepository()
    service = BookingSaga(
        Customer(),
        Event(),
        Seat(log),
        Booking(log),
        Payment(log),
        Ticket(log),
        repository,
        repository,
        SimpleNamespace(reservation_ttl_seconds=60),
    )
    workflow = Workflow(
        workflow_id="wf-seat-confirmed",
        idempotency_key="idem-seat-confirmed",
        request_hash="hash",
        customer_id="cust-1",
        event_id="e1",
        seat_ids=["A1"],
        status=WorkflowStatus.SEAT_CONFIRMED,
        booking_id="b1",
        booking_version=3,
        reservation_id="r1",
        reservation_version=2,
        payment_id="p1",
        payment_status=PaymentStatus.CAPTURED,
        amount_minor=100,
        currency="VND",
        evidence={
            "correlationId": "corr",
            "traceId": "1" * 32,
            "items": [
                {
                    "seat_id": "A1",
                    "ticket_type": "STD",
                    "unit_price": 100,
                    "currency": "VND",
                }
            ],
        },
    )
    await repository.save(workflow)

    status, body = await service.reconcile(workflow.workflow_id, context())

    assert status == 201
    assert body["status"] == "CONFIRMED"
    assert "confirm-seat" not in log
    assert "issue-ticket" in log


@pytest.mark.asyncio
async def test_reconciliation_resumes_after_ticket_issue_without_reissuing() -> None:
    from app.domain.models import PaymentStatus, Workflow, WorkflowStatus

    log: list[str] = []
    repository = InMemoryRepository()
    service = BookingSaga(
        Customer(),
        Event(),
        Seat(log),
        Booking(log),
        Payment(log),
        Ticket(log),
        repository,
        repository,
        SimpleNamespace(reservation_ttl_seconds=60),
    )
    workflow = Workflow(
        workflow_id="wf-ticket-issued",
        idempotency_key="idem-ticket-issued",
        request_hash="hash",
        customer_id="cust-1",
        event_id="e1",
        seat_ids=["A1"],
        status=WorkflowStatus.TICKETS_ISSUED,
        booking_id="b1",
        booking_version=5,
        reservation_id="r1",
        reservation_version=2,
        payment_id="p1",
        payment_status=PaymentStatus.CAPTURED,
        ticket_ids=["t1"],
        amount_minor=100,
        currency="VND",
        evidence={
            "correlationId": "corr",
            "traceId": "1" * 32,
            "items": [
                {
                    "seat_id": "A1",
                    "ticket_type": "STD",
                    "unit_price": 100,
                    "currency": "VND",
                }
            ],
        },
    )
    await repository.save(workflow)

    status, body = await service.reconcile(workflow.workflow_id, context())

    assert status == 201
    assert body["status"] == "CONFIRMED"
    assert "confirm-seat" not in log
    assert "issue-ticket" not in log
    assert "booking-tickets" in log
