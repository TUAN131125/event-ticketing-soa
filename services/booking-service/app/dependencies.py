"""FastAPI dependency accessors."""

from fastapi import Request

from app.application.service import BookingService
from app.config import Settings
from app.infrastructure.database.session import get_session_factory


def get_service(request: Request) -> BookingService:
    """Create the database-backed facade only after authentication succeeds.

    Liveness and rejected requests must not import the PostgreSQL driver or
    open an engine.  This also keeps process liveness independent from database
    readiness, while the first authorized business request initializes the
    cached SQLAlchemy factory.
    """
    service = getattr(request.app.state, "booking_service", None)
    if isinstance(service, BookingService):
        return service

    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, Settings):
        raise RuntimeError("Booking Service settings are not initialized")
    service = BookingService(settings, get_session_factory(settings))
    request.app.state.booking_service = service
    return service
