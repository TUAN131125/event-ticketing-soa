"""Runtime, service snapshot and canonical must agree on how callers authenticate.

Byte equality between a raw runtime export and the curated canonical is not expected. This
gate compares the security surface and the route surface, so CI fails if the runtime ever
drifts back to a shared secret or a route disappears.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.main import create_app
from tests.factories import build_settings

SERVICE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = SERVICE_ROOT.parents[1]
SNAPSHOT = SERVICE_ROOT / "contracts" / "openapi" / "booking-service.yaml"
CANONICAL = REPOSITORY_ROOT / "contracts" / "booking-service.yaml"
SERVICE_JWT = {"type": "http", "scheme": "bearer"}


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def routes(document: dict) -> set[tuple[str, str]]:
    return {
        (method.upper(), route)
        for route, item in document["paths"].items()
        for method in item
        if method.lower() in {"get", "post", "put", "patch", "delete"}
    }


def operation_ids(document: dict) -> set[str]:
    return {
        operation["operationId"]
        for item in document["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }


def header_names(document: dict) -> set[str]:
    names = set()
    for item in document["paths"].values():
        for operation in item.values():
            if not isinstance(operation, dict):
                continue
            for parameter in operation.get("parameters", []) or []:
                if parameter.get("in") == "header":
                    names.add(parameter.get("name"))
    return names


def test_runtime_publishes_service_jwt_and_no_shared_secret() -> None:
    schemes = create_app(build_settings()).openapi()["components"]["securitySchemes"]
    assert schemes.get("ServiceJwt") == SERVICE_JWT
    assert "serviceToken" not in schemes


def test_runtime_no_longer_requires_the_retired_headers() -> None:
    headers = header_names(create_app(build_settings()).openapi())
    assert "X-Service-Token" not in headers
    assert "X-Caller-Service" not in headers


def test_snapshot_matches_the_runtime_security_surface() -> None:
    snapshot = load(SNAPSHOT)
    runtime = create_app(build_settings()).openapi()
    assert snapshot["components"]["securitySchemes"] == runtime["components"]["securitySchemes"]
    assert routes(snapshot) == routes(runtime)
    assert operation_ids(snapshot) == operation_ids(runtime)
    assert header_names(snapshot) == header_names(runtime)


def test_canonical_declares_service_jwt_and_matches_the_route_surface() -> None:
    canonical = load(CANONICAL)
    runtime = create_app(build_settings()).openapi()
    scheme = canonical["components"]["securitySchemes"].get("ServiceJwt")
    # Canonical is the curated form and may add bearerFormat/description; the mechanism
    # itself must match the runtime.
    assert scheme is not None
    assert scheme["type"] == SERVICE_JWT["type"]
    assert scheme["scheme"] == SERVICE_JWT["scheme"]
    assert "serviceToken" not in canonical["components"]["securitySchemes"]
    assert routes(canonical) == routes(runtime)
    assert operation_ids(canonical) == operation_ids(runtime)
