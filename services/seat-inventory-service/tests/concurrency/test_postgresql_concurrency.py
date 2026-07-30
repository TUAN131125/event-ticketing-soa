from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import context, create_inventory
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError

from app.application.executor import (
    execute_database_operation,
    postgres_sqlstate,
)
from app.application.expire_reservations import expire_reservations
from app.application.reserve_seats import reserve_seats
from app.config import Settings
from app.domain.exceptions import DependencyUnavailable, SeatUnavailable
from app.domain.reservation import ReservationStatus
from app.domain.seat import SeatStatus
from app.infrastructure.database.models import ReservationModel, SeatModel
from app.infrastructure.database.session import get_engine, session_scope


@pytest.mark.integration
@pytest.mark.concurrency
def test_one_hundred_concurrent_requests_can_only_hold_a_seat_once(
    clean_database: None, test_settings: Settings
) -> None:
    create_inventory(test_settings, seat_count=1)

    def attempt(index: int) -> str:
        key = f"race-{index}"
        try:
            return execute_database_operation(
                test_settings,
                lambda session: reserve_seats(
                    session,
                    test_settings,
                    context(key, idempotency_key=key),
                    booking_id=f"BKG-RACE-{index}",
                    event_id="EVT-TEST",
                    seat_ids=("A-001",),
                    hold_seconds=10,
                ),
            ).reservation_id
        except SeatUnavailable:
            return "UNAVAILABLE"

    with ThreadPoolExecutor(max_workers=30) as pool:
        outcomes = list(pool.map(attempt, range(100)))

    winners = [value for value in outcomes if value != "UNAVAILABLE"]
    assert len(winners) == 1
    with session_scope(test_settings) as session:
        active = session.execute(
            select(func.count())
            .select_from(ReservationModel)
            .where(ReservationModel.status == ReservationStatus.ACTIVE)
        ).scalar_one()
        seat = session.get(SeatModel, ("EVT-TEST", "A-001"))
    assert active == 1
    assert seat is not None and seat.status == SeatStatus.HELD


@pytest.mark.integration
@pytest.mark.concurrency
def test_two_expiry_workers_do_not_expire_a_reservation_twice(
    clean_database: None, test_settings: Settings
) -> None:
    create_inventory(test_settings, seat_count=8)
    for index in range(1, 9):
        key = f"expire-{index}"
        execute_database_operation(
            test_settings,
            lambda session, current=index, current_key=key: reserve_seats(
                session,
                test_settings,
                context(current_key, idempotency_key=current_key),
                booking_id=f"BKG-EXP-{current}",
                event_id="EVT-TEST",
                seat_ids=(f"A-{current:03d}",),
                hold_seconds=1,
            ),
        )
    time.sleep(1.2)

    def expire(worker: int):
        return execute_database_operation(
            test_settings,
            lambda session: expire_reservations(
                session,
                test_settings,
                context(f"worker-{worker}"),
                batch_size=8,
            ),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(expire, (1, 2)))

    expired_ids = [
        reservation_id
        for result in results
        for reservation_id in result.reservation_ids
    ]
    assert len(expired_ids) == 8
    assert len(set(expired_ids)) == 8
    with session_scope(test_settings) as session:
        statuses = set(session.execute(select(SeatModel.status)).scalars())
    assert statuses == {SeatStatus.AVAILABLE}


@pytest.mark.integration
@pytest.mark.concurrency
def test_lock_timeout_is_fail_closed_and_retryable(
    clean_database: None, test_settings: Settings
) -> None:
    create_inventory(test_settings, seat_count=1)
    engine = get_engine(test_settings)
    with engine.connect() as blocker:
        transaction = blocker.begin()
        blocker.execute(
            text(
                "SELECT 1 FROM seat.seats "
                "WHERE event_id='EVT-TEST' AND seat_id='A-001' FOR UPDATE"
            )
        )
        with pytest.raises(DependencyUnavailable) as captured:
            execute_database_operation(
                test_settings,
                lambda session: reserve_seats(
                    session,
                    test_settings,
                    context("locked", idempotency_key="locked"),
                    booking_id="BKG-LOCKED",
                    event_id="EVT-TEST",
                    seat_ids=("A-001",),
                    hold_seconds=10,
                ),
            )
        transaction.rollback()
    assert captured.value.retryable is True
    with session_scope(test_settings) as session:
        seat = session.get(SeatModel, ("EVT-TEST", "A-001"))
    assert seat is not None and seat.status == SeatStatus.AVAILABLE


@pytest.mark.integration
@pytest.mark.concurrency
def test_postgresql_detects_and_aborts_a_real_deadlock(
    clean_database: None, test_settings: Settings
) -> None:
    create_inventory(test_settings, seat_count=2)
    engine = get_engine(test_settings)
    first = engine.connect()
    second = engine.connect()
    first_tx = first.begin()
    second_tx = second.begin()
    try:
        first.execute(text("SET LOCAL deadlock_timeout = '100ms'"))
        second.execute(text("SET LOCAL deadlock_timeout = '100ms'"))
        first.execute(
            text(
                "SELECT 1 FROM seat.seats WHERE event_id='EVT-TEST' "
                "AND seat_id='A-001' FOR UPDATE"
            )
        )
        second.execute(
            text(
                "SELECT 1 FROM seat.seats WHERE event_id='EVT-TEST' "
                "AND seat_id='A-002' FOR UPDATE"
            )
        )

        def request_other_lock(connection, seat_id: str) -> str:
            try:
                connection.execute(
                    text(
                        "SELECT 1 FROM seat.seats WHERE event_id='EVT-TEST' "
                        f"AND seat_id='{seat_id}' FOR UPDATE"
                    )
                )
                return "OK"
            except OperationalError as exc:
                return postgres_sqlstate(exc) or "UNKNOWN"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(
                pool.map(
                    lambda args: request_other_lock(*args),
                    ((first, "A-002"), (second, "A-001")),
                )
            )
        assert sorted(outcomes) == ["40P01", "OK"]
    finally:
        if first_tx.is_active:
            first_tx.rollback()
        if second_tx.is_active:
            second_tx.rollback()
        first.close()
        second.close()
