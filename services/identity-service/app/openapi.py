"""Serve the reviewed Identity contract as the runtime OpenAPI document."""

from __future__ import annotations

from typing import Any

import yaml
from fastapi import FastAPI

from app.config import Settings


def install_contract_openapi(application: FastAPI, settings: Settings) -> None:
    """Make /openapi.json use the repository-root canonical contract."""

    def custom_openapi() -> dict[str, Any]:
        if application.openapi_schema is not None:
            return application.openapi_schema
        document = yaml.safe_load(settings.openapi_path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise RuntimeError("Identity OpenAPI contract must be a mapping")
        application.openapi_schema = document
        return document

    application.openapi = custom_openapi  # type: ignore[method-assign]


def route_operation_ids(application: FastAPI) -> dict[tuple[str, str], str]:
    """Return actual FastAPI routes for contract-alignment tests."""

    result: dict[tuple[str, str], str] = {}

    def collect(routes: list[Any]) -> None:
        for route in routes:
            included = getattr(route, "original_router", None)
            if included is not None:
                collect(list(included.routes))
                continue
            methods = getattr(route, "methods", None)
            operation_id = getattr(route, "operation_id", None)
            path = getattr(route, "path", None)
            if not methods or not operation_id or not path:
                continue
            for method in methods:
                if method in {"HEAD", "OPTIONS"}:
                    continue
                result[(method.upper(), path)] = operation_id

    collect(list(application.routes))
    return result
