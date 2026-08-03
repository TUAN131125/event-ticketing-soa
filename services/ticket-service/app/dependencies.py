"""FastAPI dependency accessors."""

from fastapi import Request

from app.application.service import TicketService


def get_service(request: Request) -> TicketService:
    service = getattr(request.app.state, "ticket_service", None)
    if not isinstance(service, TicketService):
        raise RuntimeError("Ticket Service is not initialized")
    return service
