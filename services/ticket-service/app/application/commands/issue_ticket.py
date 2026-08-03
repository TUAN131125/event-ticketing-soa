"""Atomically issue one ticket per seat for a confirmed booking."""

from sqlalchemy.orm import Session

from app.application.common import (
    event_payload,
    existing_issue_definition,
    issue_definition_payload,
    prepare_transaction,
    replay_or_lock,
    save_replay,
    validate_context,
)
from app.config import Settings
from app.domain.entities import Ticket
from app.domain.enums import TicketEventType
from app.domain.exceptions import BookingTicketConflict, SeatTicketConflict
from app.domain.rules import (
    advisory_lock_id,
    canonical_request_hash,
    normalize_ticket_definitions,
    validate_identifier,
)
from app.domain.value_objects import RequestContext, TicketDefinition
from app.infrastructure.database.repositories import (
    acquire_advisory_lock,
    append_audit,
    append_outbox_event,
    database_now,
    entity_to_model,
    get_ticket_by_event_seat,
    get_tickets_by_booking,
    model_to_entity,
    next_ticket_id,
)

SCOPE = "IssueTickets"


def issue_tickets(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    booking_id: str,
    customer_id: str,
    event_id: str,
    payment_id: str,
    definitions: tuple[TicketDefinition, ...],
) -> tuple[Ticket, ...]:
    key = validate_context(context, idempotency_key)
    booking_id = validate_identifier(booking_id, "bookingId")
    customer_id = validate_identifier(customer_id, "customerId")
    event_id = validate_identifier(event_id, "eventId")
    payment_id = validate_identifier(payment_id, "paymentId")
    definitions = normalize_ticket_definitions(definitions)
    request = issue_definition_payload(
        booking_id=booking_id,
        customer_id=customer_id,
        event_id=event_id,
        payment_id=payment_id,
        definitions=definitions,
    )
    request_hash = canonical_request_hash(request)

    with session.begin():
        prepare_transaction(session, settings)
        now = database_now(session)
        replay = replay_or_lock(
            session, scope=SCOPE, key=key, request_hash=request_hash, now=now
        )
        if replay is not None:
            return replay

        acquire_advisory_lock(session, advisory_lock_id("TicketBooking", booking_id))
        existing_models = get_tickets_by_booking(session, booking_id, for_update=True)
        if existing_models:
            existing = tuple(model_to_entity(model) for model in existing_models)
            if existing_issue_definition(existing) != request:
                raise BookingTicketConflict(booking_id)
            save_replay(
                session,
                settings=settings,
                scope=SCOPE,
                key=key,
                request_hash=request_hash,
                tickets=existing,
                resource_id=booking_id,
                now=now,
            )
            return existing

        for definition in definitions:
            acquire_advisory_lock(
                session,
                advisory_lock_id("TicketEventSeat", f"{event_id}:{definition.seat_id}"),
            )
            if get_ticket_by_event_seat(session, event_id, definition.seat_id):
                raise SeatTicketConflict(event_id, definition.seat_id)

        tickets = tuple(
            Ticket.issue(
                ticket_id=next_ticket_id(session),
                booking_id=booking_id,
                customer_id=customer_id,
                event_id=event_id,
                payment_id=payment_id,
                seat_id=definition.seat_id,
                seat_label=definition.seat_label,
                ticket_type=definition.ticket_type,
                now=now,
            )
            for definition in definitions
        )
        for ticket in tickets:
            session.add(entity_to_model(ticket))
            append_audit(
                session,
                ticket=ticket,
                operation=SCOPE,
                previous_status=None,
                caller_service=context.caller_service,
                actor_id=context.actor_id,
                correlation_id=context.correlation_id,
                idempotency_key=key,
            )
            append_outbox_event(
                session,
                ticket=ticket,
                event_type=TicketEventType.ISSUED,
                payload=event_payload(ticket),
                correlation_id=context.correlation_id,
                now=now,
            )
        save_replay(
            session,
            settings=settings,
            scope=SCOPE,
            key=key,
            request_hash=request_hash,
            tickets=tickets,
            resource_id=booking_id,
            now=now,
        )
        return tickets
