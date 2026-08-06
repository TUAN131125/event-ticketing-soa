from __future__ import annotations

from collections.abc import Callable
from typing import Any
from types import MethodType

from fastapi import FastAPI

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
_PUBLIC_PATHS = frozenset(
    {
        "/api/auth/register",
        "/api/auth/login",
        "/api/events",
        "/api/events/{eventId}",
        "/api/events/{eventId}/seat-map",
        "/api/health",
        "/health/live",
        "/health/ready",
    }
)
_COOKIE_AUTH_PATHS = frozenset({"/api/auth/refresh", "/api/auth/logout"})


def install_security_openapi(app: FastAPI) -> None:
    """Enrich the actual FastAPI schema with the gateway security boundary.

    This function never loads or substitutes a canonical YAML document. It starts from
    FastAPI's generated operation/request/response schema and only adds the security
    schemes that are enforced by the request handlers. Contract parity tests therefore
    continue to detect response-model or route drift.
    """

    generated: Callable[[], dict[str, Any]] = app.openapi

    def openapi(_application: FastAPI) -> dict[str, Any]:
        schema = generated()
        components = schema.setdefault("components", {})
        schemes = components.setdefault("securitySchemes", {})
        schemes.update(
            {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": (
                        "Short-lived Identity user JWT. The ESB verifies signature, issuer, "
                        "audience, expiry, subject and roles."
                    ),
                },
                "RefreshCookie": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "identity_refresh",
                    "description": "HttpOnly refresh-session cookie issued through the ESB auth façade.",
                },
                "CsrfCookie": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "identity_csrf",
                    "description": "Double-submit CSRF cookie issued by Identity through the ESB.",
                },
                "CsrfHeader": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-CSRF-Token",
                    "description": "Must equal the identity_csrf cookie for refresh and logout.",
                },
            }
        )

        for path, path_item in schema.get("paths", {}).items():
            if not isinstance(path_item, dict):
                continue
            for method, operation in path_item.items():
                if method not in _HTTP_METHODS or not isinstance(operation, dict):
                    continue
                if path in _PUBLIC_PATHS:
                    operation["security"] = []
                elif path in _COOKIE_AUTH_PATHS:
                    operation["security"] = [
                        {"RefreshCookie": [], "CsrfCookie": [], "CsrfHeader": []}
                    ]
                else:
                    operation["security"] = [{"BearerAuth": []}]
        return schema

    app.openapi = MethodType(openapi, app)
