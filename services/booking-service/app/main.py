"""FastAPI entrypoint for Booking Service."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app import __version__
from app.api.health import create_health_router
from app.api.router import create_api_router
from app.application.common import prepare_transaction
from app.application.service import BookingService
from app.config import Settings, get_settings
from app.infrastructure.database.repositories import booking_counts_by_status
from app.infrastructure.database.session import dispose_engine, get_session_factory
from app.middleware.correlation_id import correlation_middleware
from app.middleware.error_handler import install_error_handlers
from app.middleware.logging import access_log_middleware
from app.observability.logs import configure_logging
from app.observability.metrics import BOOKINGS_BY_STATUS

LOGGER = logging.getLogger("booking.metrics")


def create_app(settings: Settings | None = None) -> FastAPI:
    current = settings or get_settings()
    configure_logging(current.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.draining = False
        application.state.settings = current
        application.state.booking_service = BookingService(
            current, get_session_factory(current)
        )
        try:
            yield
        finally:
            application.state.draining = True
            dispose_engine(current)

    application = FastAPI(
        title="Booking Service",
        version=__version__,
        docs_url="/docs" if current.docs_enabled else None,
        openapi_url="/openapi.json" if current.docs_enabled else None,
        lifespan=lifespan,
    )
    application.middleware("http")(access_log_middleware)
    application.middleware("http")(correlation_middleware)
    application.include_router(create_health_router(current))
    application.include_router(create_api_router())

    @application.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        try:
            service: BookingService = application.state.booking_service
            with service.session_factory() as session:
                with session.begin():
                    prepare_transaction(session, current)
                    for status_name in (
                        "PENDING",
                        "CONFIRMED",
                        "FAILED",
                        "CANCELLED",
                    ):
                        BOOKINGS_BY_STATUS.labels(status_name).set(0)
                    for status_name, count in booking_counts_by_status(session):
                        BOOKINGS_BY_STATUS.labels(status_name).set(count)
        except Exception:
            LOGGER.warning("Unable to refresh booking status metrics", exc_info=True)
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    install_error_handlers(application)
    return application


app = create_app()
