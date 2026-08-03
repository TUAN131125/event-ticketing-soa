"""PostgreSQL primitives used by booking command/query handlers."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.domain.entities import Booking
from app.domain.enums import BookingEventType, BookingStatus, PaymentStatus
from app.domain.value_objects import BookingItem
from app.infrastructure.database.models import (
    BookingAuditModel,
    BookingItemModel,
    BookingModel,
    IdempotencyRecordModel,
    OutboxEventModel,
)


def set_local_timeouts(
    session: Session, *, lock_timeout_ms: int, statement_timeout_ms: int
) -> None:
    session.execute(
        text("SELECT set_config('lock_timeout', :value, true)"),
        {"value": f"{lock_timeout_ms}ms"},
    )
    session.execute(
        text("SELECT set_config('statement_timeout', :value, true)"),
        {"value": f"{statement_timeout_ms}ms"},
    )


def database_now(session: Session) -> datetime:
    return cast(datetime, session.scalar(select(func.clock_timestamp())))


def acquire_advisory_lock(session: Session, lock_id: int) -> None:
    session.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": lock_id})


def next_booking_id(session: Session) -> str:
    value = session.execute(
        text("SELECT nextval('booking.booking_id_seq')")
    ).scalar_one()
    return f"BK{int(value):08d}"


def get_booking_model(
    session: Session, booking_id: str, *, for_update: bool = False
) -> BookingModel | None:
    statement = (
        select(BookingModel)
        .where(BookingModel.booking_id == booking_id)
        .options(selectinload(BookingModel.items))
    )
    if for_update:
        statement = statement.with_for_update(of=BookingModel)
    return session.scalar(statement)


def get_booking_by_reservation(
    session: Session, reservation_id: str, *, for_update: bool = False
) -> BookingModel | None:
    statement = (
        select(BookingModel)
        .where(BookingModel.reservation_id == reservation_id)
        .options(selectinload(BookingModel.items))
    )
    if for_update:
        statement = statement.with_for_update(of=BookingModel)
    return session.scalar(statement)


def list_booking_models(
    session: Session,
    *,
    page: int,
    page_size: int,
    customer_id: str | None,
    event_id: str | None,
    status: BookingStatus | None,
    search: str | None,
) -> tuple[list[BookingModel], int]:
    filters: list[Any] = []
    if customer_id:
        filters.append(BookingModel.customer_id == customer_id)
    if event_id:
        filters.append(BookingModel.event_id == event_id)
    if status:
        filters.append(BookingModel.status == status)
    if search:
        value = f"%{search.strip()}%"
        filters.append(
            or_(
                BookingModel.booking_id.ilike(value),
                BookingModel.customer_id.ilike(value),
                BookingModel.event_id.ilike(value),
                BookingModel.reservation_id.ilike(value),
            )
        )
    total = int(
        session.scalar(select(func.count()).select_from(BookingModel).where(*filters))
        or 0
    )
    statement = (
        select(BookingModel)
        .where(*filters)
        .options(selectinload(BookingModel.items))
        .order_by(BookingModel.created_at.desc(), BookingModel.booking_id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(session.scalars(statement).all()), total


def get_idempotency_record(
    session: Session, scope: str, key: str
) -> IdempotencyRecordModel | None:
    return session.scalar(
        select(IdempotencyRecordModel)
        .where(
            IdempotencyRecordModel.scope == scope,
            IdempotencyRecordModel.idempotency_key == key,
        )
        .with_for_update()
    )


def save_idempotency_record(
    session: Session,
    *,
    scope: str,
    key: str,
    request_hash: str,
    response_body: dict[str, Any],
    resource_id: str,
    now: datetime,
    ttl_seconds: int,
) -> None:
    session.add(
        IdempotencyRecordModel(
            scope=scope,
            idempotency_key=key,
            request_hash=request_hash,
            status="COMPLETED",
            response_body=response_body,
            resource_id=resource_id,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
    )


def append_audit(
    session: Session,
    *,
    booking: Booking,
    operation: str,
    previous_status: BookingStatus | None,
    caller_service: str,
    actor_id: str | None,
    correlation_id: str,
    idempotency_key: str,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        BookingAuditModel(
            booking_id=booking.booking_id,
            operation=operation,
            previous_status=previous_status,
            new_status=booking.status,
            caller_service=caller_service,
            actor_id=actor_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            resource_version=booking.resource_version,
            details=details or {},
        )
    )


def append_outbox_event(
    session: Session,
    *,
    booking: Booking,
    event_type: BookingEventType,
    payload: dict[str, Any],
    correlation_id: str,
    now: datetime,
) -> None:
    session.add(
        OutboxEventModel(
            event_id=str(uuid.uuid4()),
            aggregate_id=booking.booking_id,
            aggregate_type="Booking",
            aggregate_version=booking.resource_version,
            event_type=event_type,
            payload=payload,
            correlation_id=correlation_id,
            occurred_at=now,
        )
    )


def model_to_entity(model: BookingModel) -> Booking:
    return Booking(
        booking_id=model.booking_id,
        customer_id=model.customer_id,
        event_id=model.event_id,
        reservation_id=model.reservation_id,
        payment_method=model.payment_method,
        items=tuple(
            BookingItem(
                seat_id=item.seat_id,
                ticket_type=item.ticket_type,
                unit_price=Decimal(item.unit_price),
            )
            for item in model.items
        ),
        total_amount=Decimal(model.total_amount),
        currency=model.currency,
        status=BookingStatus(model.status),
        payment_status=PaymentStatus(model.payment_status),
        resource_version=model.resource_version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        payment_id=model.payment_id,
        failure_code=model.failure_code,
        failure_reason=model.failure_reason,
        cancellation_reason=model.cancellation_reason,
        confirmed_at=model.confirmed_at,
        cancelled_at=model.cancelled_at,
    )


def entity_to_model(booking: Booking) -> BookingModel:
    return BookingModel(
        booking_id=booking.booking_id,
        customer_id=booking.customer_id,
        event_id=booking.event_id,
        reservation_id=booking.reservation_id,
        payment_method=booking.payment_method,
        status=booking.status,
        payment_status=booking.payment_status,
        total_amount=booking.total_amount,
        currency=booking.currency,
        payment_id=booking.payment_id,
        failure_code=booking.failure_code,
        failure_reason=booking.failure_reason,
        cancellation_reason=booking.cancellation_reason,
        resource_version=booking.resource_version,
        created_at=booking.created_at,
        updated_at=booking.updated_at,
        confirmed_at=booking.confirmed_at,
        cancelled_at=booking.cancelled_at,
        items=[
            BookingItemModel(
                seat_id=item.seat_id,
                ticket_type=item.ticket_type,
                unit_price=item.unit_price,
                created_at=booking.created_at,
            )
            for item in booking.items
        ],
    )


def apply_entity(model: BookingModel, booking: Booking) -> None:
    model.status = booking.status
    model.payment_status = booking.payment_status
    model.payment_id = booking.payment_id
    model.failure_code = booking.failure_code
    model.failure_reason = booking.failure_reason
    model.cancellation_reason = booking.cancellation_reason
    model.resource_version = booking.resource_version
    model.updated_at = booking.updated_at
    model.confirmed_at = booking.confirmed_at
    model.cancelled_at = booking.cancelled_at


def booking_counts_by_status(session: Session) -> Sequence[tuple[str, int]]:
    return tuple(
        (str(status), int(count))
        for status, count in session.execute(
            select(BookingModel.status, func.count())
            .group_by(BookingModel.status)
            .order_by(BookingModel.status)
        )
    )
