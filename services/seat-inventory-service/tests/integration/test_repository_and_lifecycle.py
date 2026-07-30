from __future__ import annotations

import time

import pytest
from conftest import context, create_inventory
from sqlalchemy import func, select

from app.application.confirm_seats import confirm_seats
from app.application.extend_reservation import extend_reservation
from app.application.release_seats import release_seats
from app.application.reserve_seats import reserve_seats
from app.config import Settings
from app.domain.exceptions import (
    IdempotencyConflict,
    ReservationExpired,
    SeatUnavailable,
)
from app.domain.reservation import ReservationStatus
from app.domain.seat import SeatStatus
from app.infrastructure.database.models import (
    IdempotencyRecordModel,
    ReservationModel,
    SeatAuditModel,
    SeatModel,
)
from app.infrastructure.database.session import session_scope


def reserve(
    settings: Settings,
    *,
    booking_id: str,
    seat_ids: tuple[str, ...],
    key: str,
    hold_seconds: int = 10,
):
    with session_scope(settings) as session:
        return reserve_seats(
            session,
            settings,
            context(key, idempotency_key=key),
            booking_id=booking_id,
            event_id="EVT-TEST",
            seat_ids=seat_ids,
            hold_seconds=hold_seconds,
        )


@pytest.mark.integration
def test_full_reserve_extend_confirm_lifecycle_is_audited_and_idempotent(
    clean_database: None, test_settings: Settings
) -> None:
    create_inventory(test_settings, seat_count=3)
    initial = reserve(
        test_settings,
        booking_id="BKG-1",
        seat_ids=("A-001", "A-002"),
        key="reserve-1",
    )
    replay = reserve(
        test_settings,
        booking_id="BKG-1",
        seat_ids=("A-001", "A-002"),
        key="reserve-1",
    )
    assert replay.reservation_id == initial.reservation_id

    with session_scope(test_settings) as session:
        extended = extend_reservation(
            session,
            test_settings,
            context("extend-1", idempotency_key="extend-1"),
            reservation_id=initial.reservation_id,
            expected_version=1,
            extension_seconds=2,
        )
    with session_scope(test_settings) as session:
        extended_replay = extend_reservation(
            session,
            test_settings,
            context("extend-1", idempotency_key="extend-1"),
            reservation_id=initial.reservation_id,
            expected_version=1,
            extension_seconds=2,
        )
    assert extended_replay == extended
    assert extended.resource_version == 2

    with session_scope(test_settings) as session:
        confirmed = confirm_seats(
            session,
            test_settings,
            context("confirm-1", idempotency_key="confirm-1"),
            reservation_id=initial.reservation_id,
            expected_version=2,
        )
    with session_scope(test_settings) as session:
        confirmed_replay = confirm_seats(
            session,
            test_settings,
            context("confirm-1-retry", idempotency_key="confirm-1-retry"),
            reservation_id=initial.reservation_id,
            expected_version=2,
        )
    assert confirmed.status == ReservationStatus.CONFIRMED
    assert confirmed_replay.reservation_id == confirmed.reservation_id

    with session_scope(test_settings) as session:
        sold = list(
            session.execute(
                select(SeatModel).where(SeatModel.seat_id.in_(["A-001", "A-002"]))
            ).scalars()
        )
        assert {seat.status for seat in sold} == {SeatStatus.SOLD}
        assert all(seat.current_reservation_id is None for seat in sold)
        audit_count = session.execute(
            select(func.count()).select_from(SeatAuditModel)
        ).scalar_one()
        idempotency_count = session.execute(
            select(func.count()).select_from(IdempotencyRecordModel)
        ).scalar_one()
    assert audit_count == 7  # 3 configure + 2 reserve + 2 confirm
    assert idempotency_count == 4


@pytest.mark.integration
def test_release_is_idempotent_and_only_releases_owned_held_seats(
    clean_database: None, test_settings: Settings
) -> None:
    create_inventory(test_settings, seat_count=2)
    held = reserve(
        test_settings,
        booking_id="BKG-RELEASE",
        seat_ids=("A-001",),
        key="reserve-release",
    )
    with session_scope(test_settings) as session:
        released = release_seats(
            session,
            test_settings,
            context("release-1", idempotency_key="release-1"),
            reservation_id=held.reservation_id,
            reason_code="PAYMENT_FAILED",
        )
    with session_scope(test_settings) as session:
        replay = release_seats(
            session,
            test_settings,
            context("release-2", idempotency_key="release-2"),
            reservation_id=held.reservation_id,
            reason_code="PAYMENT_FAILED",
        )
        seat = session.get(SeatModel, ("EVT-TEST", "A-001"))
    assert released.status == ReservationStatus.RELEASED
    assert replay.status == ReservationStatus.RELEASED
    assert seat is not None
    assert seat.status == SeatStatus.AVAILABLE
    assert seat.current_reservation_id is None


@pytest.mark.integration
def test_idempotency_key_reuse_with_different_payload_is_conflict(
    clean_database: None, test_settings: Settings
) -> None:
    create_inventory(test_settings, seat_count=3)
    reserve(
        test_settings,
        booking_id="BKG-IDEM",
        seat_ids=("A-001",),
        key="same-key",
    )
    with pytest.raises(IdempotencyConflict):
        reserve(
            test_settings,
            booking_id="BKG-IDEM-OTHER",
            seat_ids=("A-002",),
            key="same-key",
        )


@pytest.mark.integration
def test_multi_seat_reserve_rolls_back_when_one_seat_is_unavailable(
    clean_database: None, test_settings: Settings
) -> None:
    create_inventory(test_settings, seat_count=2, blocked={2})
    with pytest.raises(SeatUnavailable):
        reserve(
            test_settings,
            booking_id="BKG-ATOMIC",
            seat_ids=("A-001", "A-002"),
            key="reserve-atomic",
        )

    with session_scope(test_settings) as session:
        seats = list(
            session.execute(select(SeatModel).order_by(SeatModel.seat_id)).scalars()
        )
        reservations = session.execute(
            select(func.count()).select_from(ReservationModel)
        ).scalar_one()
        idempotency = session.execute(
            select(func.count()).select_from(IdempotencyRecordModel)
        ).scalar_one()
    assert [seat.status for seat in seats] == [
        SeatStatus.AVAILABLE,
        SeatStatus.BLOCKED,
    ]
    assert reservations == 0
    assert idempotency == 0


@pytest.mark.integration
def test_confirm_after_database_ttl_fails_closed(
    clean_database: None, test_settings: Settings
) -> None:
    create_inventory(test_settings, seat_count=1)
    held = reserve(
        test_settings,
        booking_id="BKG-EXPIRE",
        seat_ids=("A-001",),
        key="reserve-expire",
        hold_seconds=1,
    )
    time.sleep(1.2)
    with session_scope(test_settings) as session:
        with pytest.raises(ReservationExpired):
            confirm_seats(
                session,
                test_settings,
                context("late-confirm", idempotency_key="late-confirm"),
                reservation_id=held.reservation_id,
                expected_version=1,
            )

    with session_scope(test_settings) as session:
        reservation = session.get(ReservationModel, held.reservation_id)
        seat = session.get(SeatModel, ("EVT-TEST", "A-001"))
    assert reservation is not None and reservation.status == ReservationStatus.ACTIVE
    assert seat is not None and seat.status == SeatStatus.HELD
