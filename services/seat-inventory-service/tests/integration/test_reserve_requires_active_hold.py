"""ReserveSeats may only return a reservation that is still an ACTIVE hold.

UNIQUE(booking_id) means a booking owns at most one reservation, so a repeat ReserveSeats
for a booking whose hold has ended used to hand back that dead reservation as a success.
The caller then believed it held seats it did not hold. These tests pin the guard, and each
one also asserts that the seats themselves were left untouched.
"""

from __future__ import annotations

import time

import pytest
from conftest import context, create_inventory
from sqlalchemy import func, select

from app.application.confirm_seats import confirm_seats
from app.application.release_seats import release_seats
from app.application.reserve_seats import reserve_seats
from app.config import Settings
from app.domain.exceptions import InvalidReservationState, ReservationExpired
from app.domain.reservation import ReservationStatus
from app.domain.seat import SeatStatus
from app.infrastructure.database.models import ReservationModel, SeatModel
from app.infrastructure.database.session import session_scope

EVENT_ID = "EVT-TEST"


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
            event_id=EVENT_ID,
            seat_ids=seat_ids,
            hold_seconds=hold_seconds,
        )


def seat_state(settings: Settings, seat_id: str) -> tuple[SeatStatus, str | None]:
    with session_scope(settings) as session:
        seat = session.get(SeatModel, (EVENT_ID, seat_id))
        assert seat is not None
        return seat.status, seat.current_reservation_id


def reservation_count(settings: Settings) -> int:
    with session_scope(settings) as session:
        return session.execute(
            select(func.count()).select_from(ReservationModel)
        ).scalar_one()


@pytest.mark.integration
def test_active_reservation_replays_for_the_same_booking_and_seats(
    clean_database: None, test_settings: Settings
) -> None:
    create_inventory(test_settings, seat_count=2)
    first = reserve(
        test_settings,
        booking_id="BKG-ACTIVE",
        seat_ids=("A-001",),
        key="active-first",
    )
    # A different idempotency key takes the get_reservation_by_booking path rather than the
    # stored-response path, which is the branch the guard protects.
    replay = reserve(
        test_settings,
        booking_id="BKG-ACTIVE",
        seat_ids=("A-001",),
        key="active-second",
    )

    assert first.status == ReservationStatus.ACTIVE
    assert replay.status == ReservationStatus.ACTIVE
    assert replay.reservation_id == first.reservation_id
    assert reservation_count(test_settings) == 1
    assert seat_state(test_settings, "A-001") == (
        SeatStatus.HELD,
        first.reservation_id,
    )


@pytest.mark.integration
def test_released_reservation_is_not_returned_as_a_successful_reservation(
    clean_database: None, test_settings: Settings
) -> None:
    create_inventory(test_settings, seat_count=2)
    held = reserve(
        test_settings,
        booking_id="BKG-RELEASED",
        seat_ids=("A-001",),
        key="released-first",
    )
    with session_scope(test_settings) as session:
        release_seats(
            session,
            test_settings,
            context("release-it", idempotency_key="release-it"),
            reservation_id=held.reservation_id,
            reason_code="PAYMENT_FAILED",
        )

    with pytest.raises(InvalidReservationState) as raised:
        reserve(
            test_settings,
            booking_id="BKG-RELEASED",
            seat_ids=("A-001",),
            key="released-second",
        )

    assert raised.value.code == "INVALID_RESERVATION_STATE"
    assert raised.value.retryable is False
    # The release already freed the seat; the refused reserve must not have re-held it,
    # and must not have created a second reservation for the booking.
    assert seat_state(test_settings, "A-001") == (SeatStatus.AVAILABLE, None)
    assert reservation_count(test_settings) == 1


@pytest.mark.integration
def test_confirmed_reservation_is_not_treated_as_active(
    clean_database: None, test_settings: Settings
) -> None:
    create_inventory(test_settings, seat_count=2)
    held = reserve(
        test_settings,
        booking_id="BKG-CONFIRMED",
        seat_ids=("A-001",),
        key="confirmed-first",
    )
    with session_scope(test_settings) as session:
        confirm_seats(
            session,
            test_settings,
            context("confirm-it", idempotency_key="confirm-it"),
            reservation_id=held.reservation_id,
            expected_version=held.resource_version,
        )

    with pytest.raises(InvalidReservationState):
        reserve(
            test_settings,
            booking_id="BKG-CONFIRMED",
            seat_ids=("A-001",),
            key="confirmed-second",
        )

    # The seat stays SOLD: a refused reserve never rewinds a confirmed sale.
    assert seat_state(test_settings, "A-001") == (SeatStatus.SOLD, None)
    assert reservation_count(test_settings) == 1
    with session_scope(test_settings) as session:
        reservation = session.get(ReservationModel, held.reservation_id)
        assert reservation is not None
        assert reservation.status == ReservationStatus.CONFIRMED


@pytest.mark.integration
def test_expired_hold_is_not_returned_as_a_successful_reservation(
    clean_database: None, test_settings: Settings
) -> None:
    create_inventory(test_settings, seat_count=2)
    held = reserve(
        test_settings,
        booking_id="BKG-EXPIRED",
        seat_ids=("A-001",),
        key="expired-first",
        hold_seconds=1,
    )
    time.sleep(1.2)

    with pytest.raises(ReservationExpired) as raised:
        reserve(
            test_settings,
            booking_id="BKG-EXPIRED",
            seat_ids=("A-001",),
            key="expired-second",
        )

    assert raised.value.code == "RESERVATION_EXPIRED"
    assert raised.value.retryable is False
    assert reservation_count(test_settings) == 1
    with session_scope(test_settings) as session:
        reservation = session.get(ReservationModel, held.reservation_id)
        assert reservation is not None
        # The sweeper, not ReserveSeats, is what transitions the row; the guard only
        # refuses to report the stale hold as a success.
        assert reservation.status == ReservationStatus.ACTIVE


@pytest.mark.integration
def test_stored_response_is_not_replayed_after_the_hold_ends(
    clean_database: None, test_settings: Settings
) -> None:
    """Same idempotency key, so this exercises the stored-response branch."""
    create_inventory(test_settings, seat_count=2)
    held = reserve(
        test_settings,
        booking_id="BKG-REPLAY",
        seat_ids=("A-001",),
        key="replay-key",
    )
    with session_scope(test_settings) as session:
        release_seats(
            session,
            test_settings,
            context("replay-release", idempotency_key="replay-release"),
            reservation_id=held.reservation_id,
            reason_code="PAYMENT_FAILED",
        )

    with pytest.raises(InvalidReservationState):
        reserve(
            test_settings,
            booking_id="BKG-REPLAY",
            seat_ids=("A-001",),
            key="replay-key",
        )

    assert seat_state(test_settings, "A-001") == (SeatStatus.AVAILABLE, None)
