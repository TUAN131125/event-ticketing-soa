"""PostgreSQL primitives used by ticket command/query handlers."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.domain.entities import Ticket
from app.domain.enums import TicketEventType, TicketStatus
from app.infrastructure.database.models import (
    IdempotencyRecordModel,
    OutboxEventModel,
    TicketAuditModel,
    TicketModel,
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


def next_ticket_id(session: Session) -> str:
    value = session.execute(text("SELECT nextval('ticket.ticket_id_seq')")).scalar_one()
    return f"TKT{int(value):09d}"


def get_ticket_model(
    session: Session, ticket_id: str, *, for_update: bool = False
) -> TicketModel | None:
    statement = select(TicketModel).where(TicketModel.ticket_id == ticket_id)
    if for_update:
        statement = statement.with_for_update(of=TicketModel)
    return session.scalar(statement)


def get_tickets_by_booking(
    session: Session, booking_id: str, *, for_update: bool = False
) -> list[TicketModel]:
    statement = (
        select(TicketModel)
        .where(TicketModel.booking_id == booking_id)
        .order_by(TicketModel.seat_id, TicketModel.ticket_id)
    )
    if for_update:
        statement = statement.with_for_update(of=TicketModel)
    return list(session.scalars(statement).all())


def get_ticket_by_event_seat(
    session: Session, event_id: str, seat_id: str
) -> TicketModel | None:
    return session.scalar(
        select(TicketModel)
        .where(
            TicketModel.event_id == event_id,
            TicketModel.seat_id == seat_id,
            TicketModel.status != TicketStatus.CANCELLED.value,
        )
        .with_for_update()
    )


def list_ticket_models(
    session: Session,
    *,
    page: int,
    page_size: int,
    booking_id: str | None,
    customer_id: str | None,
    event_id: str | None,
    status: TicketStatus | None,
    search: str | None,
) -> tuple[list[TicketModel], int]:
    filters: list[Any] = []
    if booking_id:
        filters.append(TicketModel.booking_id == booking_id)
    if customer_id:
        filters.append(TicketModel.customer_id == customer_id)
    if event_id:
        filters.append(TicketModel.event_id == event_id)
    if status:
        filters.append(TicketModel.status == status.value)
    if search:
        value = f"%{search}%"
        filters.append(
            or_(
                TicketModel.ticket_id.ilike(value),
                TicketModel.booking_id.ilike(value),
                TicketModel.customer_id.ilike(value),
                TicketModel.seat_id.ilike(value),
            )
        )
    total = int(
        session.scalar(select(func.count()).select_from(TicketModel).where(*filters))
        or 0
    )
    statement = (
        select(TicketModel)
        .where(*filters)
        .order_by(TicketModel.issued_at.desc(), TicketModel.ticket_id.desc())
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
    ticket: Ticket,
    operation: str,
    previous_status: TicketStatus | None,
    caller_service: str,
    actor_id: str | None,
    correlation_id: str,
    idempotency_key: str,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        TicketAuditModel(
            ticket_id=ticket.ticket_id,
            operation=operation,
            previous_status=previous_status.value if previous_status else None,
            new_status=ticket.status.value,
            caller_service=caller_service,
            actor_id=actor_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            resource_version=ticket.resource_version,
            details=details or {},
        )
    )


def append_outbox_event(
    session: Session,
    *,
    ticket: Ticket,
    event_type: TicketEventType,
    payload: dict[str, Any],
    correlation_id: str,
    now: datetime,
) -> None:
    session.add(
        OutboxEventModel(
            event_id=str(uuid.uuid4()),
            aggregate_id=ticket.ticket_id,
            aggregate_type="Ticket",
            aggregate_version=ticket.resource_version,
            event_type=event_type.value,
            payload=payload,
            correlation_id=correlation_id,
            occurred_at=now,
        )
    )


def model_to_entity(model: TicketModel) -> Ticket:
    return Ticket(
        ticket_id=model.ticket_id,
        booking_id=model.booking_id,
        customer_id=model.customer_id,
        event_id=model.event_id,
        payment_id=model.payment_id,
        seat_id=model.seat_id,
        seat_label=model.seat_label,
        ticket_type=model.ticket_type,
        status=TicketStatus(model.status),
        qr_version=model.qr_version,
        resource_version=model.resource_version,
        issued_at=model.issued_at,
        updated_at=model.updated_at,
        checked_in_at=model.checked_in_at,
        checked_in_gate_id=model.checked_in_gate_id,
        checked_in_by=model.checked_in_by,
        cancelled_at=model.cancelled_at,
        cancellation_reason=model.cancellation_reason,
    )


def entity_to_model(ticket: Ticket) -> TicketModel:
    return TicketModel(
        ticket_id=ticket.ticket_id,
        booking_id=ticket.booking_id,
        customer_id=ticket.customer_id,
        event_id=ticket.event_id,
        payment_id=ticket.payment_id,
        seat_id=ticket.seat_id,
        seat_label=ticket.seat_label,
        ticket_type=ticket.ticket_type,
        status=ticket.status.value,
        qr_version=ticket.qr_version,
        resource_version=ticket.resource_version,
        issued_at=ticket.issued_at,
        updated_at=ticket.updated_at,
        checked_in_at=ticket.checked_in_at,
        checked_in_gate_id=ticket.checked_in_gate_id,
        checked_in_by=ticket.checked_in_by,
        cancelled_at=ticket.cancelled_at,
        cancellation_reason=ticket.cancellation_reason,
    )


def apply_entity(model: TicketModel, ticket: Ticket) -> None:
    model.status = ticket.status.value
    model.qr_version = ticket.qr_version
    model.resource_version = ticket.resource_version
    model.updated_at = ticket.updated_at
    model.checked_in_at = ticket.checked_in_at
    model.checked_in_gate_id = ticket.checked_in_gate_id
    model.checked_in_by = ticket.checked_in_by
    model.cancelled_at = ticket.cancelled_at
    model.cancellation_reason = ticket.cancellation_reason


def ticket_counts_by_status(session: Session) -> Sequence[tuple[str, int]]:
    return tuple(
        (str(status), int(count))
        for status, count in session.execute(
            select(TicketModel.status, func.count())
            .group_by(TicketModel.status)
            .order_by(TicketModel.status)
        )
    )
