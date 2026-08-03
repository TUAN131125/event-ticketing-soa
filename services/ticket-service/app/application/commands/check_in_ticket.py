"""Atomic check-in with role authorization and QR verification."""

from datetime import datetime
from typing import cast

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
from app.domain.exceptions import AlreadyCheckedIn, TicketNotFound
from app.domain.rules import (
    canonical_request_hash,
    validate_expected_version,
    validate_identifier,
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
from app.security.authorization import authorize_check_in
from app.security.qr_tokens import verify_qr_token

SCOPE = "CheckInTicket"


def check_in_ticket(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    ticket_id: str,
    qr_token: str,
    gate_id: str,
    expected_version: int,
) -> Ticket:
    key = validate_context(context, idempotency_key)
    actor_id = authorize_check_in(context)
    ticket_id = validate_identifier(ticket_id, "ticketId")
    gate_id = validate_identifier(gate_id, "gateId")
    expected_version = validate_expected_version(expected_version)
    request_hash = canonical_request_hash(
        {
            "ticketId": ticket_id,
            "qrToken": qr_token,
            "gateId": gate_id,
            "expectedVersion": expected_version,
            "actorId": actor_id,
        }
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
        verify_qr_token(
            qr_token,
            expected_ticket_id=ticket.ticket_id,
            expected_qr_version=ticket.qr_version,
            signing_key=settings.qr_signing_key,
        )
        if ticket.status == TicketStatus.CHECKED_IN:
            if (
                ticket.checked_in_gate_id == gate_id
                and ticket.checked_in_by == actor_id
            ):
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
            raise AlreadyCheckedIn(
                checked_in_at=cast(datetime, ticket.checked_in_at).isoformat(),
                gate_id=ticket.checked_in_gate_id or "unknown",
            )
        previous = ticket.status
        ticket.check_in(
            gate_id=gate_id,
            checked_in_by=actor_id,
            expected_version=expected_version,
            now=now,
        )
        apply_entity(model, ticket)
        append_audit(
            session,
            ticket=ticket,
            operation=SCOPE,
            previous_status=previous,
            caller_service=context.caller_service,
            actor_id=actor_id,
            correlation_id=context.correlation_id,
            idempotency_key=key,
            details={"gateId": gate_id},
        )
        append_outbox_event(
            session,
            ticket=ticket,
            event_type=TicketEventType.CHECKED_IN,
            payload={
                **event_payload(ticket),
                "gateId": gate_id,
                "checkedInBy": actor_id,
            },
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
