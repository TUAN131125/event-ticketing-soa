"""FastAPI entrypoint for Payment Service."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from libs.platform_security import HmacRequestVerifier
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app import __version__
from app.api.health import create_health_router
from app.api.router import create_api_router
from app.application.common import prepare_transaction
from app.application.service import PaymentService
from app.config import Settings, get_settings
from app.infrastructure.database.repositories import payment_counts_by_status
from app.infrastructure.database.session import dispose_engine, get_session_factory
from app.middleware.correlation_id import correlation_middleware
from app.middleware.error_handler import install_error_handlers
from app.middleware.logging import access_log_middleware
from app.observability.logs import configure_logging
from app.observability.metrics import PAYMENTS_BY_STATUS

LOGGER = logging.getLogger("payment.metrics")
STATUS_NAMES = (
    "PENDING",
    "AUTHORIZED",
    "CAPTURED",
    "FAILED",
    "CANCELLED",
    "PARTIALLY_REFUNDED",
    "REFUNDED",
)


def create_app(settings: Settings | None = None) -> FastAPI:
    current = settings or get_settings()
    configure_logging(current.log_level)
    service_jwt_verifier = current.service_jwt.verifier()
    provider_hmac_verifier = HmacRequestVerifier(current.provider_hmac_secret)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.draining = False
        application.state.settings = current
        application.state.service_jwt_verifier = service_jwt_verifier
        application.state.provider_hmac_verifier = provider_hmac_verifier
        application.state.payment_service = PaymentService(
            current, get_session_factory(current)
        )
        try:
            yield
        finally:
            application.state.draining = True
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
        try:
            service: PaymentService = application.state.payment_service
            with service.session_factory() as session:
                with session.begin():
                    prepare_transaction(session, current)
                    for status_name in STATUS_NAMES:
                        PAYMENTS_BY_STATUS.labels(status_name).set(0)
                    for status_name, count in payment_counts_by_status(session):
                        PAYMENTS_BY_STATUS.labels(status_name).set(count)
        except Exception:
            LOGGER.warning("Unable to refresh payment status metrics", exc_info=True)
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    install_error_handlers(application)
    return application
