"""FastAPI entrypoint for Identity and Access Service."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from app import __version__
from app.api.health import create_health_router
from app.api.router import create_api_router
from app.application.service import IdentityService
from app.config import Settings, get_settings
from app.infrastructure.database.session import dispose_engine, get_session_factory
from app.middleware.correlation_id import context_middleware
from app.middleware.error_handler import install_error_handlers
from app.middleware.logging import access_log_middleware
from app.observability.logs import configure_logging
from app.observability.metrics import ACTIVE_REFRESH_SESSIONS
from app.openapi import install_contract_openapi
from app.schemas.responses import JwkSet
from app.security.passwords import PasswordService
from app.security.tokens import TokenService


def _build_identity_service(settings: Settings) -> IdentityService:
    return IdentityService(
        settings,
        get_session_factory(settings),
        PasswordService(settings),
        TokenService(settings),
    )


def _identity_service(application: FastAPI) -> IdentityService:
    service = getattr(application.state, "identity_service", None)
    if not isinstance(service, IdentityService):
        raise RuntimeError("identity service is not initialized")
    return service


def create_app(settings: Settings | None = None) -> FastAPI:
    current = settings or get_settings()
    configure_logging(current.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.draining = False
        application.state.identity_service = _build_identity_service(current)
        try:
            yield
        finally:
            application.state.draining = True
            dispose_engine(current)

    docs_url = "/docs" if current.docs_enabled else None
    openapi_url = "/openapi.json" if current.docs_enabled else None
    application = FastAPI(
        title="Identity and Access Service",
        version=__version__,
        docs_url=docs_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    # Starlette executes the last registered middleware first. Context must be
    # outermost so correlation variables remain bound while access logs run.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(current.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-CSRF-Token",
            "X-Correlation-ID",
            "traceparent",
            # Declared as required by /auth/register and /admin/users/{userId}/roles.
            "Idempotency-Key",
            "If-Match",
        ],
        expose_headers=["X-Correlation-ID", "X-Trace-ID", "ETag"],
    )
    application.add_middleware(BaseHTTPMiddleware, dispatch=access_log_middleware)
    application.add_middleware(BaseHTTPMiddleware, dispatch=context_middleware)

    application.include_router(create_health_router(current))
    application.include_router(create_api_router(current))

    @application.get(
        "/.well-known/jwks.json",
        response_model=JwkSet,
        tags=["authentication"],
        operation_id="getIdentityJwks",
    )
    def jwks() -> Response:
        return Response(
            content=json.dumps(_identity_service(application).jwks()),
            media_type="application/jwk-set+json",
            headers={"Cache-Control": "public, max-age=300"},
        )

    @application.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        try:
            ACTIVE_REFRESH_SESSIONS.set(
                _identity_service(application).active_refresh_session_count()
            )
        except Exception:
            ACTIVE_REFRESH_SESSIONS.set(0)
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    install_error_handlers(application)
    install_contract_openapi(application, current)
    return application
