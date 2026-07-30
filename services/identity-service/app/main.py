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
from app.infrastructure.database.repositories import active_refresh_session_count
from app.infrastructure.database.session import dispose_engine, get_session_factory
from app.middleware.correlation_id import context_middleware
from app.middleware.error_handler import install_error_handlers
from app.middleware.logging import access_log_middleware
from app.observability.logs import configure_logging
from app.observability.metrics import ACTIVE_REFRESH_SESSIONS
from app.security.passwords import PasswordService
from app.security.tokens import TokenService


def create_app(settings: Settings | None = None) -> FastAPI:
    current = settings or get_settings()
    configure_logging(current.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.draining = False
        password_service = PasswordService(current)
        token_service = TokenService(current)
        session_factory = get_session_factory(current)
        application.state.identity_service = IdentityService(
            current, session_factory, password_service, token_service
        )
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
    application.add_middleware(BaseHTTPMiddleware, dispatch=context_middleware)
    application.add_middleware(BaseHTTPMiddleware, dispatch=access_log_middleware)
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
        ],
        expose_headers=["X-Correlation-ID", "X-Trace-ID"],
    )
    application.include_router(create_health_router(current))
    application.include_router(create_api_router(current))

    @application.get(
        "/.well-known/jwks.json", tags=["authentication"], operation_id="jwks"
    )
    def jwks() -> Response:
        service = application.state.identity_service
        return Response(
            content=json.dumps(service.tokens.jwks()),
            media_type="application/jwk-set+json",
            headers={"Cache-Control": "public, max-age=300"},
        )

    @application.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        try:
            service: IdentityService = application.state.identity_service
            with service._sessions() as session:
                ACTIVE_REFRESH_SESSIONS.set(active_refresh_session_count(session))
        except Exception:
            ACTIVE_REFRESH_SESSIONS.set(0)
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    install_error_handlers(application)
    return application


app = create_app()
