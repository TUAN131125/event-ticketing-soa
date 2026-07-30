from __future__ import annotations

import pytest
from conftest import context, create_inventory
from sqlalchemy import func, select

import app.application.reserve_seats as reserve_module
from app.application.reserve_seats import reserve_seats
from app.config import Settings
from app.domain.seat import SeatStatus
from app.infrastructure.database.models import (
    ReservationModel,
    SeatAuditModel,
    SeatModel,
)
from app.infrastructure.database.session import session_scope


@pytest.mark.integration
def test_failure_between_state_change_and_audit_rolls_back_everything(
    clean_database: None,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_inventory(test_settings, seat_count=1)

    def fail_audit(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected transaction failure")

    monkeypatch.setattr(reserve_module, "append_audit", fail_audit)
    with session_scope(test_settings) as session:
        with pytest.raises(RuntimeError, match="injected"):
            reserve_seats(
                session,
                test_settings,
                context("rollback", idempotency_key="rollback"),
                booking_id="BKG-ROLLBACK",
                event_id="EVT-TEST",
                seat_ids=("A-001",),
                hold_seconds=10,
            )

    with session_scope(test_settings) as session:
        seat = session.get(SeatModel, ("EVT-TEST", "A-001"))
        reservation_count = session.execute(
            select(func.count()).select_from(ReservationModel)
        ).scalar_one()
        audit_count = session.execute(
            select(func.count())
            .select_from(SeatAuditModel)
            .where(SeatAuditModel.operation == "ReserveSeats")
        ).scalar_one()
    assert seat is not None and seat.status == SeatStatus.AVAILABLE
    assert reservation_count == 0
    assert audit_count == 0
