"""Internal admin inventory configuration use case."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.application.common import (
    RequestContext,
    prepare_transaction,
    replay_or_lock,
    save_replay,
)
from app.config import Settings
from app.domain.exceptions import InvalidRequest, InventoryConflict
from app.domain.rules import (
    advisory_lock_id,
    canonical_request_hash,
    validate_identifier,
)
from app.domain.seat import SeatStatus
from app.infrastructure.database.models import InventoryVersionModel, SeatModel
from app.infrastructure.database.repositories import (
    acquire_advisory_lock,
    append_audit,
    database_now,
    lock_all_seats,
    lock_inventory_version,
)


@dataclass(frozen=True, slots=True)
class SeatDefinition:
    seat_id: str
    section: str
    row_label: str
    seat_number: str
    ticket_type: str
    status: SeatStatus = SeatStatus.AVAILABLE


@dataclass(frozen=True, slots=True)
class ConfigureInventoryResult:
    event_id: str
    inventory_version: int
    seat_count: int
    replayed: bool = False


SCOPE = "ConfigureInventory"


def _result_to_payload(result: ConfigureInventoryResult) -> dict[str, int | str]:
    return {
        "eventId": result.event_id,
        "inventoryVersion": result.inventory_version,
        "seatCount": result.seat_count,
    }


def _result_from_payload(payload: dict[str, object]) -> ConfigureInventoryResult:
    return ConfigureInventoryResult(
        event_id=str(payload["eventId"]),
        inventory_version=int(str(payload["inventoryVersion"])),
        seat_count=int(str(payload["seatCount"])),
        replayed=True,
    )


def configure_inventory(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    event_id: str,
    inventory_version: int,
    seats: tuple[SeatDefinition, ...],
) -> ConfigureInventoryResult:
    context.validated(require_idempotency=True)
    event_id = validate_identifier(event_id, "eventId")
    if inventory_version < 1:
        raise InvalidRequest("inventoryVersion must be at least 1")
    if not seats:
        raise InvalidRequest("Inventory must contain at least one seat")
    if len(seats) > 20_000:
        raise InvalidRequest("Inventory may contain at most 20000 seats")

    normalized: dict[str, SeatDefinition] = {}
    for definition in seats:
        seat_id = validate_identifier(definition.seat_id, "seatId")
        if seat_id in normalized:
            raise InvalidRequest(f"Duplicate seatId: {seat_id}")
        if definition.status not in {SeatStatus.AVAILABLE, SeatStatus.BLOCKED}:
            raise InvalidRequest(
                "Admin inventory may only configure AVAILABLE or BLOCKED"
            )
        normalized[seat_id] = definition

    request_hash = canonical_request_hash(
        {
            "eventId": event_id,
            "inventoryVersion": inventory_version,
            "seats": [
                [
                    seat_id,
                    normalized[seat_id].section,
                    normalized[seat_id].row_label,
                    normalized[seat_id].seat_number,
                    normalized[seat_id].ticket_type,
                    normalized[seat_id].status.value,
                ]
                for seat_id in sorted(normalized)
            ],
        }
    )
    idempotency_key = context.idempotency_key
    if idempotency_key is None:
        raise AssertionError("validated idempotency key is missing")

    with session.begin():
        prepare_transaction(session, settings)
        replay = replay_or_lock(
            session,
            scope=SCOPE,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            return _result_from_payload(replay)
        acquire_advisory_lock(session, advisory_lock_id(SCOPE, event_id))
        version_row = lock_inventory_version(session, event_id)
        now = database_now(session)
        if version_row is None:
            if inventory_version != 1:
                raise InventoryConflict("Initial inventoryVersion must be 1")
            version_row = InventoryVersionModel(
                event_id=event_id,
                inventory_version=1,
                updated_at=now,
            )
            session.add(version_row)
        elif inventory_version <= version_row.inventory_version:
            raise InventoryConflict(
                f"inventoryVersion must be greater than {version_row.inventory_version}"
            )
        else:
            version_row.inventory_version = inventory_version
            version_row.updated_at = now

        existing = {seat.seat_id: seat for seat in lock_all_seats(session, event_id)}

        for seat_id, row in existing.items():
            current_definition = normalized.get(seat_id)
            if row.status in {SeatStatus.HELD, SeatStatus.SOLD}:
                if current_definition is None or (
                    row.section != current_definition.section
                    or row.row_label != current_definition.row_label
                    or row.seat_number != current_definition.seat_number
                    or row.ticket_type != current_definition.ticket_type
                ):
                    raise InventoryConflict(
                        f"Cannot remove or modify {row.status} seat {seat_id}"
                    )
                continue
            if current_definition is None:
                append_audit(
                    session,
                    event_id=event_id,
                    seat_id=seat_id,
                    reservation_id=None,
                    booking_id=None,
                    operation="ConfigureInventory",
                    previous_status=row.status,
                    new_status=None,
                    reason_code="ADMIN_REMOVE",
                    actor_id=context.actor_id,
                    caller_service=context.caller_service,
                    correlation_id=context.correlation_id,
                    idempotency_key=context.idempotency_key,
                    resource_version=row.resource_version + 1,
                )
                session.delete(row)
                continue
            changed = (
                row.section != current_definition.section
                or row.row_label != current_definition.row_label
                or row.seat_number != current_definition.seat_number
                or row.ticket_type != current_definition.ticket_type
                or row.status != current_definition.status
            )
            if changed:
                previous = row.status
                row.section = current_definition.section
                row.row_label = current_definition.row_label
                row.seat_number = current_definition.seat_number
                row.ticket_type = current_definition.ticket_type
                row.status = current_definition.status
                row.resource_version += 1
                row.updated_at = now
                append_audit(
                    session,
                    event_id=event_id,
                    seat_id=seat_id,
                    reservation_id=None,
                    booking_id=None,
                    operation="ConfigureInventory",
                    previous_status=previous,
                    new_status=row.status,
                    reason_code="ADMIN_UPDATE",
                    actor_id=context.actor_id,
                    caller_service=context.caller_service,
                    correlation_id=context.correlation_id,
                    idempotency_key=context.idempotency_key,
                    resource_version=row.resource_version,
                )

        for seat_id in sorted(set(normalized) - set(existing)):
            definition = normalized[seat_id]
            row = SeatModel(
                event_id=event_id,
                seat_id=seat_id,
                section=definition.section,
                row_label=definition.row_label,
                seat_number=definition.seat_number,
                ticket_type=definition.ticket_type,
                status=definition.status,
                current_reservation_id=None,
                resource_version=1,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            append_audit(
                session,
                event_id=event_id,
                seat_id=seat_id,
                reservation_id=None,
                booking_id=None,
                operation="ConfigureInventory",
                previous_status=None,
                new_status=definition.status,
                reason_code="ADMIN_CREATE",
                actor_id=context.actor_id,
                caller_service=context.caller_service,
                correlation_id=context.correlation_id,
                idempotency_key=context.idempotency_key,
                resource_version=1,
            )

        result = ConfigureInventoryResult(
            event_id=event_id,
            inventory_version=inventory_version,
            seat_count=len(normalized),
        )
        save_replay(
            session,
            settings=settings,
            scope=SCOPE,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response=_result_to_payload(result),
            resource_id=event_id,
            now=now,
        )
        return result
