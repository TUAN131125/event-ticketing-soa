"""Shared application request context and idempotency helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.exceptions import IdempotencyConflict, InvalidRequest
from app.domain.reservation import ReservationStatus, ReservationView
from app.domain.rules import advisory_lock_id, validate_identifier
from app.infrastructure.database.repositories import (
    acquire_advisory_lock,
    get_idempotency_record,
    save_idempotency_record,
    set_local_timeouts,
)
from app.observability.metrics import IDEMPOTENCY_REPLAY_TOTAL


@dataclass(frozen=True, slots=True)
class RequestContext:
    correlation_id: str
    caller_service: str
    idempotency_key: str | None = None
    actor_id: str | None = None
    schema_version: str = "1"

    def validated(self, *, require_idempotency: bool = False) -> RequestContext:
        validate_identifier(self.correlation_id, "correlationId")
        validate_identifier(self.caller_service, "callerService")
        if self.actor_id:
            validate_identifier(self.actor_id, "actorId")
        # seat-inventory.xsd types schemaVersion as xs:positiveInteger, so the
        # canonical wire value is "1".
        if self.schema_version != "1":
            raise InvalidRequest("schemaVersion must be 1")
        if require_idempotency and not self.idempotency_key:
            raise InvalidRequest("idempotencyKey is required for this operation")
        if self.idempotency_key:
            validate_identifier(self.idempotency_key, "idempotencyKey")
        return self


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
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any] | None:
    acquire_advisory_lock(session, advisory_lock_id(scope, idempotency_key))
    record = get_idempotency_record(session, scope, idempotency_key)
    if record is None:
        return None
    if record.request_hash != request_hash:
        raise IdempotencyConflict()
    IDEMPOTENCY_REPLAY_TOTAL.labels(scope).inc()
    return dict(record.response_body)


def save_replay(
    session: Session,
    *,
    settings: Settings,
    scope: str,
    idempotency_key: str,
    request_hash: str,
    response: dict[str, Any],
    resource_id: str | None,
    now: datetime,
) -> None:
    save_idempotency_record(
        session,
        scope=scope,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_body=response,
        resource_id=resource_id,
        now=now,
        ttl_seconds=settings.idempotency_ttl_seconds,
    )


def reservation_to_payload(view: ReservationView) -> dict[str, Any]:
    return {
        "reservationId": view.reservation_id,
        "bookingId": view.booking_id,
        "eventId": view.event_id,
        "seatIds": list(view.seat_ids),
        "status": view.status.value,
        "expiresAt": view.expires_at.isoformat(),
        "extendCount": view.extend_count,
        "resourceVersion": view.resource_version,
        "createdAt": view.created_at.isoformat(),
        "updatedAt": view.updated_at.isoformat(),
    }


def reservation_from_payload(payload: dict[str, Any]) -> ReservationView:
    return ReservationView(
        reservation_id=str(payload["reservationId"]),
        booking_id=str(payload["bookingId"]),
        event_id=str(payload["eventId"]),
        seat_ids=tuple(str(value) for value in payload["seatIds"]),
        status=ReservationStatus(str(payload["status"])),
        expires_at=datetime.fromisoformat(str(payload["expiresAt"])),
        extend_count=int(payload["extendCount"]),
        resource_version=int(payload["resourceVersion"]),
        created_at=datetime.fromisoformat(str(payload["createdAt"])),
        updated_at=datetime.fromisoformat(str(payload["updatedAt"])),
    )
