"""FastAPI entrypoint for Payment Service."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app import __version__
from app.api.health import create_health_router
from app.api.router import create_api_router
from app.application.service import PaymentService
from app.config import Settings, get_settings
from app.domain.enums import PaymentStatus
from app.infrastructure.database.session import dispose_engine
from app.middleware.correlation_id import correlation_middleware
from app.middleware.error_handler import install_error_handlers
from app.middleware.logging import access_log_middleware
from app.observability.logs import configure_logging
from app.observability.metrics import (
    OUTBOX_EXHAUSTED,
    OUTBOX_PENDING,
    PAYMENTS_BY_STATUS,
)

LOGGER = logging.getLogger("payment.metrics")


def _refresh_database_gauges(application: FastAPI) -> None:
    """Refresh DB-backed gauges, tolerating a database that is briefly unavailable.

    A scrape must never fail because of the database, so on error the previously
    published values are left in place rather than reset to zero.
    """
    try:
        service = application.state.payment_service
        if not isinstance(service, PaymentService):
            return
        counts = service.status_counts()
        pending, exhausted = service.outbox_backlog()
    except Exception:
        LOGGER.warning("Unable to refresh payment metrics", exc_info=True)
        return
    for payment_status in PaymentStatus:
        PAYMENTS_BY_STATUS.labels(payment_status.value).set(
            counts.get(payment_status.value, 0)
        )
    OUTBOX_PENDING.set(pending)
    OUTBOX_EXHAUSTED.set(exhausted)


def create_app(settings: Settings | None = None) -> FastAPI:
    current = settings or get_settings()
    configure_logging(current.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.draining = False
        application.state.settings = current
        application.state.payment_service = None
        try:
            yield
        finally:
            application.state.draining = True
            if isinstance(application.state.payment_service, PaymentService):
                dispose_engine(current)

    application = FastAPI(
        title="Payment Service",
        version=__version__,
        description=(
            "Internal provider-neutral payment ledger. Raw card credentials are "
            "not accepted by this API."
        ),
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
        _refresh_database_gauges(application)
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    install_error_handlers(application)
    return application


app = create_app()
