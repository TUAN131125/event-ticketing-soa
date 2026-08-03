"""FastAPI dependency accessors."""

from fastapi import Request

from app.application.service import PaymentService


def get_service(request: Request) -> PaymentService:
    service = getattr(request.app.state, "payment_service", None)
    if not isinstance(service, PaymentService):
        raise RuntimeError("Payment Service is not initialized")
    return service
