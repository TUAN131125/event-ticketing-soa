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

# `context_middleware` reads both of these on every request, before routing, so they are
# never part of a route signature and FastAPI cannot discover them. They are documented
# here so the published schema describes the headers the gateway actually honours.
_CONTEXT_HEADERS = (
    {
        "name": "X-Correlation-ID",
        "in": "header",
        "required": False,
        "description": (
            "Caller-supplied correlation id, echoed on the response. The gateway "
            "generates one when the header is absent."
        ),
        "schema": {"type": "string", "minLength": 1, "maxLength": 128},
        "example": "corr-1234567890abcdef",
    },
    {
        "name": "traceparent",
        "in": "header",
        "required": False,
        "description": "W3C trace context. A new trace id is created when absent or malformed.",
        "schema": {
            "type": "string",
            "pattern": "^[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$",
        },
        "example": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
    },
)

# `parse_if_match` accepts only a quoted positive resource version and answers anything
# else with 400 INVALID_IF_MATCH. That constraint is enforced in the handler rather than
# by the route signature — deliberately, so the rejection stays a 400 instead of becoming
# FastAPI's 422 — which leaves the generated schema describing a bare string. Publishing
# the pattern here documents the rule the gateway already applies without moving where it
# is enforced. Optional occurrences are modelled by the signature as `anyOf[string, null]`;
# an absent header is not a null value on the wire, so the published schema is the string.
_IF_MATCH_SCHEMA = {"type": "string", "pattern": '^"[1-9][0-9]*"$'}


def install_security_openapi(app: FastAPI) -> None:
    """Enrich the actual FastAPI schema with the gateway security boundary.

    This function never loads or substitutes a canonical YAML document. It starts from
    FastAPI's generated operation/request/response schema and only adds the security
    schemes that are enforced by the request handlers, plus the two context headers the
    HTTP middleware reads on every request. Contract parity tests therefore continue to
    detect response-model or route drift.
    """

    generated: Callable[[], dict[str, Any]] = app.openapi

    def openapi(_application: FastAPI) -> dict[str, Any]:
        schema = generated()
        components = schema.setdefault("components", {})
        schemes = components.setdefault("securitySchemes", {})
        schemes.update(
            {
                "UserJwt": {
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
                    operation["security"] = [{"UserJwt": []}]
                declared = operation.setdefault("parameters", [])
                for parameter in declared:
                    if (
                        isinstance(parameter, dict)
                        and parameter.get("in") == "header"
                        and parameter.get("name") == "If-Match"
                    ):
                        parameter["schema"] = dict(_IF_MATCH_SCHEMA)
                already = {
                    (item.get("name"), item.get("in"))
                    for item in declared
                    if isinstance(item, dict)
                }
                declared.extend(
                    dict(header)
                    for header in _CONTEXT_HEADERS
                    if (header["name"], header["in"]) not in already
                )
        return schema

    app.openapi = MethodType(openapi, app)
