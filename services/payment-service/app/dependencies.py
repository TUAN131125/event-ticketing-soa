"""FastAPI dependency accessors with lazy database initialization."""

from fastapi import Request

from app.application.service import PaymentService
from app.infrastructure.database.session import get_session_factory


def get_service(request: Request) -> PaymentService:
    service = getattr(request.app.state, "payment_service", None)
    if isinstance(service, PaymentService):
        return service
    settings = request.app.state.settings
    service = PaymentService(settings, get_session_factory(settings))
    request.app.state.payment_service = service
    return service
