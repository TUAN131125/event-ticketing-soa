"""Shared transaction, idempotency and event-envelope helpers."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.entities import Booking
from app.domain.enums import (
    BookingStatus,
    CompensationAction,
    CompensationStatus,
    PaymentStatus,
    ReservationEvidenceStatus,
)
from app.domain.exceptions import IdempotencyConflict
from app.domain.rules import advisory_lock_id, validate_identifier
from app.domain.value_objects import BookingItem, RequestContext
from app.infrastructure.database.repositories import (
    acquire_advisory_lock,
    get_idempotency_record,
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
) -> Booking | None:
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
    return booking_from_payload(record.response_body)


def save_replay(
    session: Session,
    *,
    settings: Settings,
    scope: str,
    key: str,
    request_hash: str,
    booking: Booking,
    now: datetime,
) -> None:
    save_idempotency_record(
        session,
        scope=scope,
        key=key,
        request_hash=request_hash,
        response_body=booking_to_payload(booking),
        resource_id=booking.booking_id,
        now=now,
        ttl_seconds=settings.idempotency_ttl_seconds,
    )


def booking_to_payload(booking: Booking) -> dict[str, Any]:
    return {
        "bookingId": booking.booking_id,
        "customerId": booking.customer_id,
        "eventId": booking.event_id,
        "reservationId": booking.reservation_id,
        "paymentMethod": booking.payment_method,
        "items": [
            {
                "seatId": item.seat_id,
                "ticketType": item.ticket_type,
                "unitPrice": str(item.unit_price),
            }
            for item in booking.items
        ],
        "totalAmount": str(booking.total_amount),
        "currency": booking.currency,
        "status": booking.status.value,
        "paymentStatus": booking.payment_status.value,
        "paymentId": booking.payment_id,
        "reservationStatus": booking.reservation_status.value,
        "ticketIds": list(booking.ticket_ids),
        "failureCode": booking.failure_code,
        "failureReason": booking.failure_reason,
        "paymentFailureCode": booking.payment_failure_code,
        "cancellationReason": booking.cancellation_reason,
        "compensationStatus": booking.compensation_status.value,
        "compensationAction": booking.compensation_action.value,
        "compensationReason": booking.compensation_reason,
        "intendedTerminalStatus": (
            booking.intended_terminal_status.value
            if booking.intended_terminal_status
            else None
        ),
        "reservationVersion": booking.reservation_version,
        "resourceVersion": booking.resource_version,
        "createdAt": booking.created_at.isoformat(),
        "updatedAt": booking.updated_at.isoformat(),
        "reservationExpiresAt": _datetime_text(booking.reservation_expires_at),
        "confirmedAt": _datetime_text(booking.confirmed_at),
        "cancelledAt": _datetime_text(booking.cancelled_at),
        "reservationConfirmedAt": _datetime_text(
            booking.reservation_confirmed_at
        ),
        "reservationReleasedAt": _datetime_text(booking.reservation_released_at),
        "paymentRecordedAt": _datetime_text(booking.payment_recorded_at),
        "paymentRefundedAt": _datetime_text(booking.payment_refunded_at),
        "compensationUpdatedAt": _datetime_text(
            booking.compensation_updated_at
        ),
        "ticketsAttachedAt": _datetime_text(booking.tickets_attached_at),
        "paymentProviderReference": booking.payment_provider_reference,
        "compensationProviderReference": booking.compensation_provider_reference,
    }


def booking_from_payload(payload: dict[str, Any]) -> Booking:
    return Booking(
        booking_id=str(payload["bookingId"]),
        customer_id=str(payload["customerId"]),
        event_id=str(payload["eventId"]),
        reservation_id=_optional_text(payload.get("reservationId")),
        payment_method=_optional_text(payload.get("paymentMethod")),
        items=tuple(
            BookingItem(
                seat_id=str(item["seatId"]),
                ticket_type=str(item["ticketType"]),
                unit_price=Decimal(str(item["unitPrice"])),
            )
            for item in payload["items"]
        ),
        total_amount=Decimal(str(payload["totalAmount"])),
        currency=str(payload["currency"]),
        status=BookingStatus(str(payload["status"])),
        payment_status=PaymentStatus(str(payload["paymentStatus"])),
        reservation_status=ReservationEvidenceStatus(
            str(payload.get("reservationStatus", "PENDING"))
        ),
        compensation_status=CompensationStatus(
            str(payload.get("compensationStatus", "NOT_REQUIRED"))
        ),
        compensation_action=CompensationAction(
            str(payload.get("compensationAction", "NONE"))
        ),
        ticket_ids=tuple(str(value) for value in payload.get("ticketIds", [])),
        payment_id=_optional_text(payload.get("paymentId")),
        failure_code=_optional_text(payload.get("failureCode")),
        failure_reason=_optional_text(payload.get("failureReason")),
        payment_failure_code=_optional_text(payload.get("paymentFailureCode")),
        cancellation_reason=_optional_text(payload.get("cancellationReason")),
        compensation_reason=_optional_text(payload.get("compensationReason")),
        intended_terminal_status=(
            BookingStatus(str(payload["intendedTerminalStatus"]))
            if payload.get("intendedTerminalStatus")
            else None
        ),
        reservation_version=(
            int(payload["reservationVersion"])
            if payload.get("reservationVersion") is not None
            else None
        ),
        resource_version=int(payload["resourceVersion"]),
        created_at=datetime.fromisoformat(str(payload["createdAt"])),
        updated_at=datetime.fromisoformat(str(payload["updatedAt"])),
        reservation_expires_at=_optional_datetime(
            payload.get("reservationExpiresAt")
        ),
        confirmed_at=_optional_datetime(payload.get("confirmedAt")),
        cancelled_at=_optional_datetime(payload.get("cancelledAt")),
        reservation_confirmed_at=_optional_datetime(
            payload.get("reservationConfirmedAt")
        ),
        reservation_released_at=_optional_datetime(
            payload.get("reservationReleasedAt")
        ),
        payment_recorded_at=_optional_datetime(payload.get("paymentRecordedAt")),
        payment_refunded_at=_optional_datetime(payload.get("paymentRefundedAt")),
        compensation_updated_at=_optional_datetime(
            payload.get("compensationUpdatedAt")
        ),
        tickets_attached_at=_optional_datetime(payload.get("ticketsAttachedAt")),
        payment_provider_reference=_optional_text(
            payload.get("paymentProviderReference")
        ),
        compensation_provider_reference=_optional_text(
            payload.get("compensationProviderReference")
        ),
    )


def event_payload(booking: Booking) -> dict[str, Any]:
    return {
        "bookingId": booking.booking_id,
        "customerId": booking.customer_id,
        "eventId": booking.event_id,
        "reservationId": booking.reservation_id,
        "seatIds": [item.seat_id for item in booking.items],
        "status": booking.status.value,
        "paymentStatus": booking.payment_status.value,
        "paymentId": booking.payment_id,
        "ticketIds": list(booking.ticket_ids),
        "totalAmount": str(booking.total_amount),
        "currency": booking.currency,
        "resourceVersion": booking.resource_version,
        "occurredAt": booking.updated_at.isoformat(),
    }


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _datetime_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _optional_datetime(value: Any) -> datetime | None:
    return None if value is None else datetime.fromisoformat(str(value))
