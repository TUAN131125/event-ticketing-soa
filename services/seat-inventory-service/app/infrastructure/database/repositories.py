"""PostgreSQL repository primitives used by application handlers."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import Select, delete, func, select, text
from sqlalchemy.orm import Session

from app.domain.reservation import ReservationStatus, ReservationView
from app.domain.seat import SeatStatus, SeatView
from app.infrastructure.database.models import (
    IdempotencyRecordModel,
    InventoryVersionModel,
    ReservationItemModel,
    ReservationModel,
    SeatAuditModel,
    SeatModel,
)


def set_local_timeouts(
    session: Session, *, lock_timeout_ms: int, statement_timeout_ms: int
) -> None:
    session.execute(
        text("SELECT set_config('lock_timeout', :timeout, true)"),
        {"timeout": f"{lock_timeout_ms}ms"},
    )
    session.execute(
        text("SELECT set_config('statement_timeout', :timeout, true)"),
        {"timeout": f"{statement_timeout_ms}ms"},
    )


def database_now(session: Session) -> datetime:
    return cast(datetime, session.execute(select(func.clock_timestamp())).scalar_one())


def acquire_advisory_lock(session: Session, lock_id: int) -> None:
    session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id}
    )


def get_idempotency_record(
    session: Session, scope: str, idempotency_key: str
) -> IdempotencyRecordModel | None:
    statement = (
        select(IdempotencyRecordModel)
        .where(
            IdempotencyRecordModel.scope == scope,
            IdempotencyRecordModel.idempotency_key == idempotency_key,
        )
        .with_for_update()
    )
    return session.execute(statement).scalar_one_or_none()


def save_idempotency_record(
    session: Session,
    *,
    scope: str,
    idempotency_key: str,
    request_hash: str,
    response_body: dict[str, Any],
    resource_id: str | None,
    now: datetime,
    ttl_seconds: int,
) -> None:
    session.add(
        IdempotencyRecordModel(
            scope=scope,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            status="COMPLETED",
            response_body=response_body,
            resource_id=resource_id,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
    )


def lock_seats(
    session: Session, event_id: str, seat_ids: Sequence[str]
) -> list[SeatModel]:
    statement: Select[tuple[SeatModel]] = (
        select(SeatModel)
        .where(SeatModel.event_id == event_id, SeatModel.seat_id.in_(seat_ids))
        .order_by(SeatModel.seat_id)
        .with_for_update()
    )
    return list(session.execute(statement).scalars())


def lock_all_seats(session: Session, event_id: str) -> list[SeatModel]:
    statement = (
        select(SeatModel)
        .where(SeatModel.event_id == event_id)
        .order_by(SeatModel.seat_id)
        .with_for_update()
    )
    return list(session.execute(statement).scalars())


def get_seats(
    session: Session, event_id: str, seat_ids: Sequence[str] | None = None
) -> list[SeatModel]:
    statement = select(SeatModel).where(SeatModel.event_id == event_id)
    if seat_ids is not None:
        statement = statement.where(SeatModel.seat_id.in_(seat_ids))
    statement = statement.order_by(
        SeatModel.section, SeatModel.row_label, SeatModel.seat_number, SeatModel.seat_id
    )
    return list(session.execute(statement).scalars())


def get_inventory_version(session: Session, event_id: str) -> int | None:
    return session.execute(
        select(InventoryVersionModel.inventory_version).where(
            InventoryVersionModel.event_id == event_id
        )
    ).scalar_one_or_none()


def lock_inventory_version(
    session: Session, event_id: str
) -> InventoryVersionModel | None:
    return session.execute(
        select(InventoryVersionModel)
        .where(InventoryVersionModel.event_id == event_id)
        .with_for_update()
    ).scalar_one_or_none()


def get_reservation(
    session: Session, reservation_id: str, *, for_update: bool = False
) -> ReservationModel | None:
    statement = select(ReservationModel).where(
        ReservationModel.reservation_id == reservation_id
    )
    if for_update:
        statement = statement.with_for_update()
    return session.execute(statement).scalar_one_or_none()


def get_reservation_by_booking(
    session: Session, booking_id: str, *, for_update: bool = False
) -> ReservationModel | None:
    statement = select(ReservationModel).where(
        ReservationModel.booking_id == booking_id
    )
    if for_update:
        statement = statement.with_for_update()
    return session.execute(statement).scalar_one_or_none()


def get_reservation_seat_ids(session: Session, reservation_id: str) -> tuple[str, ...]:
    statement = (
        select(ReservationItemModel.seat_id)
        .where(ReservationItemModel.reservation_id == reservation_id)
        .order_by(ReservationItemModel.seat_id)
    )
    return tuple(session.execute(statement).scalars())


def lock_reservation_seats(session: Session, reservation_id: str) -> list[SeatModel]:
    statement = (
        select(SeatModel)
        .join(
            ReservationItemModel,
            (ReservationItemModel.event_id == SeatModel.event_id)
            & (ReservationItemModel.seat_id == SeatModel.seat_id),
        )
        .where(ReservationItemModel.reservation_id == reservation_id)
        .order_by(SeatModel.seat_id)
        .with_for_update(of=SeatModel)
    )
    return list(session.execute(statement).scalars())


def append_audit(
    session: Session,
    *,
    event_id: str,
    seat_id: str | None,
    reservation_id: str | None,
    booking_id: str | None,
    operation: str,
    previous_status: str | None,
    new_status: str | None,
    reason_code: str | None,
    actor_id: str | None,
    caller_service: str,
    correlation_id: str,
    idempotency_key: str | None,
    resource_version: int | None,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        SeatAuditModel(
            event_id=event_id,
            seat_id=seat_id,
            reservation_id=reservation_id,
            booking_id=booking_id,
            operation=operation,
            previous_status=previous_status,
            new_status=new_status,
            reason_code=reason_code,
            actor_id=actor_id,
            caller_service=caller_service,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            resource_version=resource_version,
            details=json.dumps(details, sort_keys=True) if details else None,
        )
    )


def delete_expired_idempotency_records(session: Session, now: datetime) -> int:
    result = session.execute(
        delete(IdempotencyRecordModel).where(IdempotencyRecordModel.expires_at <= now)
    )
    return int(result.rowcount or 0)


def seat_to_view(model: SeatModel) -> SeatView:
    return SeatView(
        event_id=model.event_id,
        seat_id=model.seat_id,
        section=model.section,
        row_label=model.row_label,
        seat_number=model.seat_number,
        ticket_type=model.ticket_type,
        status=SeatStatus(model.status),
        resource_version=model.resource_version,
    )


def reservation_to_view(session: Session, model: ReservationModel) -> ReservationView:
    return ReservationView(
        reservation_id=model.reservation_id,
        booking_id=model.booking_id,
        event_id=model.event_id,
        seat_ids=get_reservation_seat_ids(session, model.reservation_id),
        status=ReservationStatus(model.status),
        expires_at=model.expires_at,
        extend_count=model.extend_count,
        resource_version=model.resource_version,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
