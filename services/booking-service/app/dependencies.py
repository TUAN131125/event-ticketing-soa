"""FastAPI dependency accessors."""

from fastapi import Request

from app.application.service import BookingService


def get_service(request: Request) -> BookingService:
    service = getattr(request.app.state, "booking_service", None)
    if not isinstance(service, BookingService):
        raise RuntimeError("Booking Service is not initialized")
    return service
