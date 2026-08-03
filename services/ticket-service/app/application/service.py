"""Ticket use-case facade with bounded persistence retries."""

from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.application.commands.cancel_ticket import cancel_ticket
from app.application.commands.check_in_ticket import check_in_ticket
from app.application.commands.issue_ticket import issue_tickets
from app.application.commands.regenerate_qr import regenerate_qr
from app.application.queries.get_ticket import get_ticket
from app.application.queries.list_tickets import list_tickets
from app.config import Settings
from app.domain.entities import Ticket
from app.domain.enums import TicketStatus
from app.domain.value_objects import RequestContext, TicketDefinition, TicketPage
from app.resilience.retry import execute_database_operation


class TicketService:
    def __init__(
        self, settings: Settings, session_factory: sessionmaker[Session]
    ) -> None:
        self.settings = settings
        self._sessions = session_factory

    @property
    def session_factory(self) -> sessionmaker[Session]:
        return self._sessions

    def issue(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        booking_id: str,
        customer_id: str,
        event_id: str,
        payment_id: str,
        definitions: tuple[TicketDefinition, ...],
    ) -> tuple[Ticket, ...]:
        return self._execute(
            lambda session: issue_tickets(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                booking_id=booking_id,
                customer_id=customer_id,
                event_id=event_id,
                payment_id=payment_id,
                definitions=definitions,
            )
        )

    def cancel(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        ticket_id: str,
        reason: str,
        expected_version: int,
    ) -> Ticket:
        return self._execute(
            lambda session: cancel_ticket(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                ticket_id=ticket_id,
                reason=reason,
                expected_version=expected_version,
            )
        )

    def check_in(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        ticket_id: str,
        qr_token: str,
        gate_id: str,
        expected_version: int,
    ) -> Ticket:
        return self._execute(
            lambda session: check_in_ticket(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                ticket_id=ticket_id,
                qr_token=qr_token,
                gate_id=gate_id,
                expected_version=expected_version,
            )
        )

    def regenerate_qr(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        ticket_id: str,
        expected_version: int,
    ) -> Ticket:
        return self._execute(
            lambda session: regenerate_qr(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                ticket_id=ticket_id,
                expected_version=expected_version,
            )
        )

    def get(self, ticket_id: str) -> Ticket:
        return self._execute(
            lambda session: get_ticket(session, self.settings, ticket_id),
            max_retries=0,
        )

    def list(
        self,
        *,
        page: int,
        page_size: int,
        booking_id: str | None,
        customer_id: str | None,
        event_id: str | None,
        status: TicketStatus | None,
        search: str | None,
    ) -> TicketPage:
        return self._execute(
            lambda session: list_tickets(
                session,
                self.settings,
                page=page,
                page_size=page_size,
                booking_id=booking_id,
                customer_id=customer_id,
                event_id=event_id,
                status=status,
                search=search,
            ),
            max_retries=0,
        )

    def _execute[T](
        self,
        operation: Callable[[Session], T],
        *,
        max_retries: int = 1,
    ) -> T:
        return execute_database_operation(
            self._sessions, operation, max_retries=max_retries
        )
