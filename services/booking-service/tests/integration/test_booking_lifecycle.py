from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.application.service import BookingService
from app.domain.enums import BookingStatus, PaymentStatus
from app.domain.exceptions import IdempotencyConflict, ReservationConflict
from app.domain.value_objects import BookingItem, RequestContext
from app.infrastructure.database.models import BookingAuditModel, OutboxEventModel

pytestmark = pytest.mark.integration


def context(value: str = "COR-1") -> RequestContext:
    return RequestContext(value, "booking-orchestrator", "USER-1")


def create(
    service: BookingService,
    *,
    key: str = "CREATE-1",
    reservation_id: str = "RES-1",
    customer_id: str = "C001",
):
    return service.create(
        context(),
        idempotency_key=key,
        customer_id=customer_id,
        event_id="EV001",
        reservation_id=reservation_id,
        payment_method="CARD",
        items=(
            BookingItem("A-01", "VIP", Decimal("120.00")),
            BookingItem("A-02", "VIP", Decimal("120.00")),
        ),
        total_amount=Decimal("240.00"),
        currency="VND",
    )


def counts(service: BookingService) -> tuple[int, int]:
    with service.session_factory() as session:
        return (
            int(
                session.scalar(select(func.count()).select_from(BookingAuditModel)) or 0
            ),
            int(
                session.scalar(select(func.count()).select_from(OutboxEventModel)) or 0
            ),
        )


def test_full_lifecycle_is_persistent_audited_and_idempotent(
    service: BookingService,
) -> None:
    original = create(service)
    replay = create(service)
    assert replay.booking_id == original.booking_id
    assert counts(service) == (1, 1)

    confirmed = service.confirm(
        context("COR-2"),
        idempotency_key="CONFIRM-1",
        booking_id=original.booking_id,
        payment_id="PAY-1",
        expected_version=1,
    )
    assert confirmed.status == BookingStatus.CONFIRMED
    assert confirmed.payment_status == PaymentStatus.SUCCEEDED

    # A caller that lost the original key can still retry the same terminal command.
    retry_with_new_key = service.confirm(
        context("COR-3"),
        idempotency_key="CONFIRM-2",
        booking_id=original.booking_id,
        payment_id="PAY-1",
        expected_version=1,
    )
    assert retry_with_new_key.resource_version == 2
    assert counts(service) == (2, 2)

    cancelled = service.cancel(
        context("COR-4"),
        idempotency_key="CANCEL-1",
        booking_id=original.booking_id,
        reason="customer requested refund",
        expected_version=2,
        payment_status=PaymentStatus.REFUNDED,
    )
    assert cancelled.status == BookingStatus.CANCELLED
    assert service.get(original.booking_id).status == BookingStatus.CANCELLED
    assert counts(service) == (3, 3)


def test_idempotency_and_reservation_conflicts_are_distinguished(
    service: BookingService,
) -> None:
    create(service)
    with pytest.raises(IdempotencyConflict):
        create(service, key="CREATE-1", reservation_id="RES-2")
    with pytest.raises(ReservationConflict):
        create(service, key="CREATE-2", customer_id="C999")


def test_database_rejects_an_inconsistent_aggregate_state(
    service: BookingService,
) -> None:
    original = create(service)
    with pytest.raises(IntegrityError):
        with service.session_factory() as session:
            with session.begin():
                session.execute(
                    text(
                        "UPDATE booking.bookings SET payment_status = 'FAILED' "
                        "WHERE booking_id = :booking_id"
                    ),
                    {"booking_id": original.booking_id},
                )


@pytest.mark.concurrency
def test_concurrent_create_for_one_reservation_creates_one_aggregate(
    service: BookingService,
) -> None:
    def worker(index: int) -> str:
        return create(service, key=f"CONCURRENT-{index}").booking_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        booking_ids = list(pool.map(worker, range(16)))

    assert len(set(booking_ids)) == 1
    assert counts(service) == (1, 1)
    page = service.list(
        page=1,
        page_size=20,
        customer_id=None,
        event_id=None,
        status=None,
        search=None,
    )
    assert page.total == 1
