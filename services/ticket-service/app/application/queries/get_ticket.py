"""GetTicket query."""

from sqlalchemy.orm import Session

from app.application.common import prepare_transaction
from app.config import Settings
from app.domain.entities import Ticket
from app.domain.exceptions import TicketNotFound
from app.domain.rules import validate_identifier
from app.infrastructure.database.repositories import get_ticket_model, model_to_entity


def get_ticket(session: Session, settings: Settings, ticket_id: str) -> Ticket:
    ticket_id = validate_identifier(ticket_id, "ticketId")
    with session.begin():
        prepare_transaction(session, settings)
        model = get_ticket_model(session, ticket_id)
        if model is None:
            raise TicketNotFound(ticket_id)
        return model_to_entity(model)
