"""Shared execution pipeline for state-changing booking commands.

Every booking transition obeys the same protocol: claim the idempotency key,
replay a completed result verbatim, lock the aggregate row, apply exactly one
domain mutation, then persist audit and outbox evidence inside that single
transaction.

That protocol lives here once. A concrete command declares only what makes it
different -- its scope, its canonical request payload, how to recognise that it
has already been applied, the mutation itself, and any evidence it records.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy.orm import Session

from app.application.common import (
    prepare_transaction,
    replay_or_lock,
    save_replay,
    validate_context,
)
from app.config import Settings
from app.domain.entities import Booking
from app.domain.enums import BookingEventType
from app.domain.exceptions import BookingNotFound
from app.domain.rules import canonical_request_hash
from app.domain.value_objects import RequestContext
from app.infrastructure.database.mappers import apply_entity, model_to_entity
from app.infrastructure.database.models import BookingModel
from app.infrastructure.database.repositories import (
    append_audit,
    append_outbox_event,
    database_now,
    get_booking_model,
)


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    """A domain event to be published from the transactional outbox."""

    event_type: BookingEventType
    payload: dict[str, Any]


class BookingTransition(ABC):
    """One state-changing command against an existing booking aggregate.

    Subclasses are immutable request objects: they are built (and validated)
    from caller input, then executed by :func:`execute_transition`.
    """

    scope: ClassVar[str]

    @property
    @abstractmethod
    def booking_id(self) -> str:
        """Identifier of the aggregate this command targets."""

    @abstractmethod
    def request_payload(self) -> dict[str, Any]:
        """Canonical request fields used to hash and compare replays."""

    @abstractmethod
    def is_already_applied(self, booking: Booking) -> bool:
        """Return ``True`` when this exact command is already recorded.

        A caller that lost its idempotency key must be able to retry safely,
        so an identical outcome is treated as success rather than a conflict.

        Raises:
            InvalidRequest: the booking already records a *different* outcome
                for this step, which is a caller error and not a replay.
        """

    @abstractmethod
    def apply(self, booking: Booking, now: datetime) -> None:
        """Perform the single domain mutation this command represents."""

    def before_load(self, session: Session) -> None:
        """Acquire command-specific locks or validate unique external evidence."""

    def audit_details(self, booking: Booking) -> dict[str, Any]:
        """Command-specific evidence stored on the audit row."""
        return {}

    def outbox_event(self, booking: Booking) -> OutboxEvent | None:
        """Domain event to publish, or ``None`` when the step is internal."""
        return None


def execute_transition(
    session: Session,
    settings: Settings,
    context: RequestContext,
    transition: BookingTransition,
    *,
    idempotency_key: str,
) -> Booking:
    """Run one booking transition atomically and idempotently."""
    key = validate_context(context, idempotency_key)
    request_hash = canonical_request_hash(transition.request_payload())

    with session.begin():
        prepare_transaction(session, settings)
        now = database_now(session)

        replay = replay_or_lock(
            session,
            scope=transition.scope,
            key=key,
            request_hash=request_hash,
            now=now,
        )
        if replay is not None:
            return replay

        transition.before_load(session)
        model = get_booking_model(session, transition.booking_id, for_update=True)
        if model is None:
            raise BookingNotFound(transition.booking_id)
        booking = model_to_entity(model)

        if not transition.is_already_applied(booking):
            _apply_and_record(session, context, transition, booking, model, now, key)

        save_replay(
            session,
            settings=settings,
            scope=transition.scope,
            key=key,
            request_hash=request_hash,
            booking=booking,
            now=now,
        )
        return booking


def _apply_and_record(
    session: Session,
    context: RequestContext,
    transition: BookingTransition,
    booking: Booking,
    model: BookingModel,
    now: datetime,
    idempotency_key: str,
) -> None:
    """Mutate the aggregate and persist its audit and outbox evidence."""
    previous_status = booking.status
    transition.apply(booking, now)
    apply_entity(model, booking)
    append_audit(
        session,
        booking=booking,
        operation=transition.scope,
        previous_status=previous_status,
        caller_service=context.caller_service,
        actor_id=context.actor_id,
        correlation_id=context.correlation_id,
        idempotency_key=idempotency_key,
        details=transition.audit_details(booking),
    )
    event = transition.outbox_event(booking)
    if event is not None:
        append_outbox_event(
            session,
            booking=booking,
            event_type=event.event_type,
            payload=event.payload,
            correlation_id=context.correlation_id,
            now=now,
        )
