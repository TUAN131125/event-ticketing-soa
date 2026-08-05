"""FastAPI application factory for Customer Service."""

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from libs.platform_http import error_envelope

from app.api.router import api_router
from app.config import Settings, get_settings
from app.domain.exceptions import (
    CustomerNotFoundError,
    DuplicateEmailError,
    IdentityMappingConflictError,
    PreconditionFailedError,
)
from app.infrastructure.database.session import dispose_engine
from app.middleware.correlation_id import CorrelationIdMiddleware
from app.middleware.logging import RequestLoggingMiddleware
from app.observability.logs import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    current = settings or get_settings()
    configure_logging(current.log_level)
    application = FastAPI(title="Customer Service", version="1.0.0")
    application.state.settings = current
    application.state.service_jwt_verifier = current.service_jwt.verifier()
    application.add_middleware(RequestLoggingMiddleware)
    application.add_middleware(CorrelationIdMiddleware)
    application.include_router(api_router)

    @application.exception_handler(CustomerNotFoundError)
    async def not_found(request: Request, exc: CustomerNotFoundError) -> JSONResponse:
        return JSONResponse(
            error_envelope(request, code="CUSTOMER_NOT_FOUND", message=str(exc)),
            status_code=404,
        )

    @application.exception_handler(DuplicateEmailError)
    async def conflict(request: Request, exc: DuplicateEmailError) -> JSONResponse:
        return JSONResponse(
            error_envelope(request, code="DUPLICATE_EMAIL", message=str(exc)),
            status_code=409,
        )

    @application.exception_handler(IdentityMappingConflictError)
    async def mapping_conflict(
        request: Request, exc: IdentityMappingConflictError
    ) -> JSONResponse:
        return JSONResponse(
            error_envelope(request, code="IDENTITY_MAPPING_CONFLICT", message=str(exc)),
            status_code=409,
        )

    @application.exception_handler(PreconditionFailedError)
    async def precondition(
        request: Request, exc: PreconditionFailedError
    ) -> JSONResponse:
        return JSONResponse(
            error_envelope(request, code="PRECONDITION_FAILED", message=str(exc)),
            status_code=412,
        )

    @application.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"path": list(item["loc"]), "type": item["type"]} for item in exc.errors()
        ]
        return JSONResponse(
            error_envelope(
                request,
                code="VALIDATION_ERROR",
                message="Request validation failed",
                details=details,
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
