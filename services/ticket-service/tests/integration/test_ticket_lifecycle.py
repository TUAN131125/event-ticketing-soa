from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.application.service import TicketService
from app.domain.enums import TicketStatus
from app.domain.exceptions import (
    BookingTicketConflict,
    IdempotencyConflict,
    InvalidQrToken,
    SeatTicketConflict,
)
from app.domain.value_objects import RequestContext, TicketDefinition
from app.infrastructure.database.models import OutboxEventModel, TicketAuditModel
from app.security.qr_tokens import create_qr_token

pytestmark = pytest.mark.integration


def context(value: str = "COR-1") -> RequestContext:
    return RequestContext(value, "booking-orchestrator", "USER-1")


def staff_context(value: str = "COR-STAFF") -> RequestContext:
    return RequestContext(
        value,
        "checkin-gateway",
        "STAFF-1",
        frozenset({"CHECKIN_STAFF"}),
    )


def issue(
    service: TicketService,
    *,
    key: str = "ISSUE-1",
    booking_id: str = "BK00000001",
    payment_id: str = "PAY00000001",
    definitions: tuple[TicketDefinition, ...] | None = None,
):
    return service.issue(
        context(),
        idempotency_key=key,
        booking_id=booking_id,
        customer_id="C001",
        event_id="EV001",
        payment_id=payment_id,
        definitions=definitions
        or (
            TicketDefinition("A-01", "A-01", "VIP"),
            TicketDefinition("A-02", "A-02", "VIP"),
        ),
    )


def counts(service: TicketService) -> tuple[int, int]:
    with service.session_factory() as session:
        return (
            int(
                session.scalar(select(func.count()).select_from(TicketAuditModel)) or 0
            ),
            int(
                session.scalar(select(func.count()).select_from(OutboxEventModel)) or 0
            ),
        )


def test_full_lifecycle_is_persistent_audited_and_idempotent(
    service: TicketService,
) -> None:
    original = issue(service)
    replay = issue(service)
    assert [value.ticket_id for value in replay] == [
        value.ticket_id for value in original
    ]
    assert counts(service) == (2, 2)

    first, second = original
    old_token = create_qr_token(
        first.ticket_id, first.qr_version, service.settings.qr_signing_key
    )
    regenerated = service.regenerate_qr(
        context("COR-2"),
        idempotency_key="REGENERATE-1",
        ticket_id=first.ticket_id,
        expected_version=1,
    )
    assert regenerated.qr_version == 2
    assert regenerated.resource_version == 2
    with pytest.raises(InvalidQrToken):
        service.check_in(
            staff_context("COR-3"),
            idempotency_key="CHECKIN-OLD",
            ticket_id=first.ticket_id,
            qr_token=old_token,
            gate_id="GATE-A",
            expected_version=2,
        )

    current_token = create_qr_token(
        first.ticket_id, regenerated.qr_version, service.settings.qr_signing_key
    )
    checked_in = service.check_in(
        staff_context("COR-4"),
        idempotency_key="CHECKIN-1",
        ticket_id=first.ticket_id,
        qr_token=current_token,
        gate_id="GATE-A",
        expected_version=2,
    )
    assert checked_in.status == TicketStatus.CHECKED_IN
    retry = service.check_in(
        staff_context("COR-5"),
        idempotency_key="CHECKIN-2",
        ticket_id=first.ticket_id,
        qr_token=current_token,
        gate_id="GATE-A",
        expected_version=2,
    )
    assert retry.resource_version == 3

    cancelled = service.cancel(
        context("COR-6"),
        idempotency_key="CANCEL-1",
        ticket_id=second.ticket_id,
        reason="booking refunded",
        expected_version=1,
    )
    assert cancelled.status == TicketStatus.CANCELLED
    assert service.get(first.ticket_id).status == TicketStatus.CHECKED_IN
    assert counts(service) == (5, 5)


def test_idempotency_booking_and_event_seat_conflicts_are_distinguished(
    service: TicketService,
) -> None:
    existing = issue(service)
    with pytest.raises(IdempotencyConflict):
        issue(service, key="ISSUE-1", booking_id="BK00000002")
    with pytest.raises(BookingTicketConflict):
        issue(service, key="ISSUE-2", payment_id="PAY00000002")
    with pytest.raises(SeatTicketConflict):
        issue(
            service,
            key="ISSUE-3",
            booking_id="BK00000003",
            payment_id="PAY00000003",
            definitions=(TicketDefinition("A-01", "A-01", "VIP"),),
        )

    service.cancel(
        context("COR-CANCEL"),
        idempotency_key="CANCEL-OLD-SEAT",
        ticket_id=existing[0].ticket_id,
        reason="booking refunded",
        expected_version=1,
    )
    replacement = issue(
        service,
        key="ISSUE-4",
        booking_id="BK00000004",
        payment_id="PAY00000004",
        definitions=(TicketDefinition("A-01", "A-01", "VIP"),),
    )
    assert replacement[0].ticket_id != existing[0].ticket_id


def test_database_rejects_an_inconsistent_aggregate_state(
    service: TicketService,
) -> None:
    first = issue(service)[0]
    with pytest.raises(IntegrityError):
        with service.session_factory() as session:
            with session.begin():
                session.execute(
                    text(
                        "UPDATE ticket.tickets SET status = 'CHECKED_IN' "
                        "WHERE ticket_id = :ticket_id"
                    ),
                    {"ticket_id": first.ticket_id},
                )


@pytest.mark.concurrency
def test_concurrent_issue_for_one_booking_creates_one_ticket_set(
    service: TicketService,
) -> None:
    def worker(index: int) -> tuple[str, ...]:
        return tuple(
            value.ticket_id for value in issue(service, key=f"CONCURRENT-{index}")
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(worker, range(16)))
    assert len(set(results)) == 1
    assert counts(service) == (2, 2)
    page = service.list(
        page=1,
        page_size=20,
        booking_id="BK00000001",
        customer_id=None,
        event_id=None,
        status=None,
        search=None,
    )
    assert page.total == 2
