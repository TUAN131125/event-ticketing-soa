"""FastAPI application factory for Notification Service."""

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from libs.platform_http import error_envelope
from libs.platform_security import HmacRequestVerifier

from app.api.router import api_router
from app.config import Settings, get_settings
from app.infrastructure.database.session import dispose_engine
from app.middleware.correlation_id import CorrelationIdMiddleware
from app.middleware.logging import RequestLoggingMiddleware
from app.observability.logs import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    current = settings or get_settings()
    configure_logging(current.log_level)
    application = FastAPI(title="Notification Service", version="1.0.0")
    application.state.settings = current
    application.state.service_jwt_verifier = current.service_jwt.verifier()
    application.state.webhook_verifier = HmacRequestVerifier(
        current.webhook_hmac_secret,
        tolerance_seconds=current.webhook_tolerance_seconds,
    )
    application.add_middleware(RequestLoggingMiddleware)
    application.add_middleware(CorrelationIdMiddleware)
    application.include_router(api_router)

    @application.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            error_envelope(
                request, code="VALIDATION_ERROR", message="Request validation failed"
            ),
            status_code=422,
        )

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code = "AUTHENTICATION_FAILED" if exc.status_code == 401 else "HTTP_ERROR"
        return JSONResponse(
            error_envelope(request, code=code, message=str(exc.detail)),
            status_code=exc.status_code,
        )

    application.router.add_event_handler("shutdown", dispose_engine)
    return application
