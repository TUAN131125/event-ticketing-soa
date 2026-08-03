"""Atomic and idempotent CancelTicket command."""

from sqlalchemy.orm import Session

from app.application.common import (
    event_payload,
    prepare_transaction,
    replay_or_lock,
    save_replay,
    validate_context,
)
from app.config import Settings
from app.domain.entities import Ticket
from app.domain.enums import TicketEventType, TicketStatus
from app.domain.exceptions import InvalidRequest, TicketNotFound
from app.domain.rules import (
    canonical_request_hash,
    validate_expected_version,
    validate_identifier,
    validate_reason,
)
from app.domain.value_objects import RequestContext
from app.infrastructure.database.repositories import (
    append_audit,
    append_outbox_event,
    apply_entity,
    database_now,
    get_ticket_model,
    model_to_entity,
)

SCOPE = "CancelTicket"


def cancel_ticket(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    ticket_id: str,
    reason: str,
    expected_version: int,
) -> Ticket:
    key = validate_context(context, idempotency_key)
    ticket_id = validate_identifier(ticket_id, "ticketId")
    reason = validate_reason(reason)
    expected_version = validate_expected_version(expected_version)
    request_hash = canonical_request_hash(
        {"ticketId": ticket_id, "reason": reason, "expectedVersion": expected_version}
    )
    with session.begin():
        prepare_transaction(session, settings)
        now = database_now(session)
        replay = replay_or_lock(
            session, scope=SCOPE, key=key, request_hash=request_hash, now=now
        )
        if replay is not None:
            return replay[0]
        model = get_ticket_model(session, ticket_id, for_update=True)
        if model is None:
            raise TicketNotFound(ticket_id)
        ticket = model_to_entity(model)
        if ticket.status == TicketStatus.CANCELLED:
            if ticket.cancellation_reason != reason:
                raise InvalidRequest("Ticket already records another cancellation")
            save_replay(
                session,
                settings=settings,
                scope=SCOPE,
                key=key,
                request_hash=request_hash,
                tickets=(ticket,),
                resource_id=ticket_id,
                now=now,
            )
            return ticket
        previous = ticket.status
        ticket.cancel(reason=reason, expected_version=expected_version, now=now)
        apply_entity(model, ticket)
        append_audit(
            session,
            ticket=ticket,
            operation=SCOPE,
            previous_status=previous,
            caller_service=context.caller_service,
            actor_id=context.actor_id,
            correlation_id=context.correlation_id,
            idempotency_key=key,
            details={"reason": reason},
        )
        append_outbox_event(
            session,
            ticket=ticket,
            event_type=TicketEventType.CANCELLED,
            payload={**event_payload(ticket), "reason": reason},
            correlation_id=context.correlation_id,
            now=now,
        )
        save_replay(
            session,
            settings=settings,
            scope=SCOPE,
            key=key,
            request_hash=request_hash,
            tickets=(ticket,),
            resource_id=ticket_id,
            now=now,
        )
        return ticket
