"""Shared transaction, idempotency and event-envelope helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.entities import Ticket
from app.domain.exceptions import IdempotencyConflict
from app.domain.rules import advisory_lock_id, validate_identifier
from app.domain.value_objects import RequestContext, TicketDefinition
from app.infrastructure.database.repositories import (
    acquire_advisory_lock,
    get_idempotency_record,
    get_ticket_model,
    model_to_entity,
    save_idempotency_record,
    set_local_timeouts,
)
from app.observability.metrics import IDEMPOTENCY_REPLAY_TOTAL


def validate_context(context: RequestContext, idempotency_key: str) -> str:
    validate_identifier(context.correlation_id, "correlationId")
    validate_identifier(context.caller_service, "callerService")
    if context.actor_id:
        validate_identifier(context.actor_id, "actorId")
    return validate_identifier(idempotency_key, "idempotencyKey")


def prepare_transaction(session: Session, settings: Settings) -> None:
    set_local_timeouts(
        session,
        lock_timeout_ms=settings.db_lock_timeout_ms,
        statement_timeout_ms=settings.db_statement_timeout_ms,
    )


def replay_or_lock(
    session: Session,
    *,
    scope: str,
    key: str,
    request_hash: str,
    now: datetime,
) -> tuple[Ticket, ...] | None:
    acquire_advisory_lock(session, advisory_lock_id(scope, key))
    record = get_idempotency_record(session, scope, key)
    if record is None:
        return None
    if record.expires_at <= now:
        session.delete(record)
        session.flush()
        return None
    if record.request_hash != request_hash:
        raise IdempotencyConflict()
    IDEMPOTENCY_REPLAY_TOTAL.labels(scope).inc()
    snapshots = tuple(
        ticket_from_payload(value) for value in record.response_body["tickets"]
    )
    current: list[Ticket] = []
    for snapshot in snapshots:
        model = get_ticket_model(session, snapshot.ticket_id, for_update=True)
        if model is None:
            return snapshots
        current.append(model_to_entity(model))
    return tuple(current)


def save_replay(
    session: Session,
    *,
    settings: Settings,
    scope: str,
    key: str,
    request_hash: str,
    tickets: tuple[Ticket, ...],
    resource_id: str,
    now: datetime,
) -> None:
    save_idempotency_record(
        session,
        scope=scope,
        key=key,
        request_hash=request_hash,
        response_body={"tickets": [ticket_to_payload(value) for value in tickets]},
        resource_id=resource_id,
        now=now,
        ttl_seconds=settings.idempotency_ttl_seconds,
    )


def ticket_to_payload(ticket: Ticket) -> dict[str, Any]:
    return {
        "ticketId": ticket.ticket_id,
        "bookingId": ticket.booking_id,
        "customerId": ticket.customer_id,
        "eventId": ticket.event_id,
        "paymentId": ticket.payment_id,
        "seatId": ticket.seat_id,
        "seatLabel": ticket.seat_label,
        "ticketType": ticket.ticket_type,
        "status": ticket.status.value,
        "qrVersion": ticket.qr_version,
        "resourceVersion": ticket.resource_version,
        "issuedAt": ticket.issued_at.isoformat(),
        "updatedAt": ticket.updated_at.isoformat(),
        "checkedInAt": (
            ticket.checked_in_at.isoformat() if ticket.checked_in_at else None
        ),
        "checkedInGateId": ticket.checked_in_gate_id,
        "checkedInBy": ticket.checked_in_by,
        "cancelledAt": (
            ticket.cancelled_at.isoformat() if ticket.cancelled_at else None
        ),
        "cancellationReason": ticket.cancellation_reason,
    }


def ticket_from_payload(payload: dict[str, Any]) -> Ticket:
    from app.domain.enums import TicketStatus

    return Ticket(
        ticket_id=str(payload["ticketId"]),
        booking_id=str(payload["bookingId"]),
        customer_id=str(payload["customerId"]),
        event_id=str(payload["eventId"]),
        payment_id=str(payload["paymentId"]),
        seat_id=str(payload["seatId"]),
        seat_label=str(payload["seatLabel"]),
        ticket_type=str(payload["ticketType"]),
        status=TicketStatus(str(payload["status"])),
        qr_version=int(payload["qrVersion"]),
        resource_version=int(payload["resourceVersion"]),
        issued_at=datetime.fromisoformat(str(payload["issuedAt"])),
        updated_at=datetime.fromisoformat(str(payload["updatedAt"])),
        checked_in_at=_optional_datetime(payload.get("checkedInAt")),
        checked_in_gate_id=_optional_text(payload.get("checkedInGateId")),
        checked_in_by=_optional_text(payload.get("checkedInBy")),
        cancelled_at=_optional_datetime(payload.get("cancelledAt")),
        cancellation_reason=_optional_text(payload.get("cancellationReason")),
    )


def event_payload(ticket: Ticket) -> dict[str, Any]:
    return {
        "ticketId": ticket.ticket_id,
        "bookingId": ticket.booking_id,
        "customerId": ticket.customer_id,
        "eventId": ticket.event_id,
        "paymentId": ticket.payment_id,
        "seatId": ticket.seat_id,
        "seatLabel": ticket.seat_label,
        "ticketType": ticket.ticket_type,
        "status": ticket.status.value,
        "qrVersion": ticket.qr_version,
        "resourceVersion": ticket.resource_version,
        "occurredAt": ticket.updated_at.isoformat(),
    }


def issue_definition_payload(
    *,
    booking_id: str,
    customer_id: str,
    event_id: str,
    payment_id: str,
    definitions: tuple[TicketDefinition, ...],
) -> dict[str, object]:
    return {
        "bookingId": booking_id,
        "customerId": customer_id,
        "eventId": event_id,
        "paymentId": payment_id,
        "tickets": [
            {
                "seatId": value.seat_id,
                "seatLabel": value.seat_label,
                "ticketType": value.ticket_type,
            }
            for value in definitions
        ],
    }


def existing_issue_definition(tickets: tuple[Ticket, ...]) -> dict[str, object]:
    first = tickets[0]
    return issue_definition_payload(
        booking_id=first.booking_id,
        customer_id=first.customer_id,
        event_id=first.event_id,
        payment_id=first.payment_id,
        definitions=tuple(
            TicketDefinition(value.seat_id, value.seat_label, value.ticket_type)
            for value in sorted(tickets, key=lambda item: item.seat_id)
        ),
    )


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_datetime(value: Any) -> datetime | None:
    return None if value is None else datetime.fromisoformat(str(value))
