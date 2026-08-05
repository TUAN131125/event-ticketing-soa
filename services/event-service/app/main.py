"""FastAPI application factory for Event Service."""

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from libs.platform_http import error_envelope

from app.api.router import api_router
from app.config import Settings, get_settings
from app.domain.exceptions import EventNotFoundError, InvalidStateTransitionError
from app.infrastructure.database.session import dispose_engine
from app.middleware.correlation_id import CorrelationIdMiddleware
from app.middleware.logging import RequestLoggingMiddleware
from app.observability.logs import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    current = settings or get_settings()
    configure_logging(current.log_level)
    application = FastAPI(title="Event Service", version="1.0.0")
    application.state.settings = current
    application.state.service_jwt_verifier = current.service_jwt.verifier()
    application.add_middleware(RequestLoggingMiddleware)
    application.add_middleware(CorrelationIdMiddleware)
    application.include_router(api_router)

    def domain_error(
        request: Request, code: str, message: str, status: int
    ) -> JSONResponse:
        return JSONResponse(
            error_envelope(request, code=code, message=message), status_code=status
        )

    @application.exception_handler(EventNotFoundError)
    async def not_found(request: Request, exc: EventNotFoundError) -> JSONResponse:
        return domain_error(request, "EVENT_NOT_FOUND", str(exc), 404)

    @application.exception_handler(InvalidStateTransitionError)
    async def conflict(
        request: Request, exc: InvalidStateTransitionError
    ) -> JSONResponse:
        return domain_error(request, "INVALID_STATE_TRANSITION", str(exc), 409)

    @application.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        return domain_error(
            request, "VALIDATION_ERROR", "Request validation failed", 422
        )

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code = "AUTHENTICATION_FAILED" if exc.status_code == 401 else "HTTP_ERROR"
        return domain_error(request, code, str(exc.detail), exc.status_code)

    application.router.add_event_handler("shutdown", dispose_engine)
    return application
