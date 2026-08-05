"""Small provider-side OpenAPI conformance assertions shared by service tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from libs.platform_security import ServiceJwtValidationSettings

HTTP_METHODS = frozenset({"delete", "get", "head", "options", "patch", "post", "put"})


def _operations(document: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (path, method): operation
        for path, path_item in document["paths"].items()
        for method, operation in path_item.items()
        if method in HTTP_METHODS
    }


def _resolve(document: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    current = value
    visited: set[str] = set()
    while "$ref" in current:
        reference = current["$ref"]
        if not reference.startswith("#/") or reference in visited:
            break
        visited.add(reference)
        target: Any = document
        for part in reference[2:].split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        current = target
    return current


def _required_headers(
    document: dict[str, Any], path: str, operation: dict[str, Any]
) -> set[str]:
    parameters = [
        *document["paths"][path].get("parameters", []),
        *operation.get("parameters", []),
    ]
    headers = {
        parameter["name"].lower()
        for raw in parameters
        for parameter in [_resolve(document, raw)]
        if parameter.get("in") == "header" and parameter.get("required") is True
    }
    effective_security = operation.get("security", document.get("security", []))
    schemes = document.get("components", {}).get("securitySchemes", {})
    for requirement in effective_security:
        for name in requirement:
            scheme = schemes.get(name, {})
            if scheme.get("type") == "apiKey" and scheme.get("in") == "header":
                headers.add(str(scheme["name"]).lower())
    return headers


def _effective_security(
    document: dict[str, Any], operation: dict[str, Any]
) -> set[str]:
    requirements = operation.get("security", document.get("security", []))
    return {name for requirement in requirements for name in requirement}


def _json_schema(
    document: dict[str, Any], content_owner: dict[str, Any]
) -> dict[str, Any] | None:
    content = content_owner.get("content", {})
    media = content.get("application/json")
    if not media or not media.get("schema"):
        return None
    return _resolve(document, media["schema"])


def _schema_surface(
    document: dict[str, Any], schema: dict[str, Any] | None
) -> tuple[Any, ...]:
    if schema is None:
        return ("none",)
    schema = _resolve(document, schema)
    if "allOf" in schema:
        surfaces = [_schema_surface(document, item) for item in schema["allOf"]]
        properties = frozenset().union(
            *(item[1] for item in surfaces if item[0] == "object")
        )
        required = frozenset().union(
            *(item[2] for item in surfaces if item[0] == "object")
        )
        return "object", properties, required
    if schema.get("type") == "array":
        return "array", _schema_surface(document, schema.get("items", {}))
    return (
        "object",
        frozenset(schema.get("properties", {})),
        frozenset(schema.get("required", [])),
    )


def _surface_matches(actual: tuple[Any, ...], expected: tuple[Any, ...]) -> bool:
    if expected == ("object", frozenset(), frozenset()):
        return actual[0] == "object"
    return actual == expected


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _assert_payload_surface(
    runtime: dict[str, Any], canonical: dict[str, Any], operation_key: tuple[str, str]
) -> None:
    path, method = operation_key
    runtime_operation = runtime["paths"][path][method]
    canonical_operation = canonical["paths"][path][method]
    runtime_request = runtime_operation.get("requestBody")
    canonical_request = canonical_operation.get("requestBody")
    _require(
        bool(runtime_request) == bool(canonical_request),
        f"{operation_key} request body",
    )
    if runtime_request and canonical_request:
        _require(
            _surface_matches(
                _schema_surface(runtime, _json_schema(runtime, runtime_request)),
                _schema_surface(canonical, _json_schema(canonical, canonical_request)),
            ),
            f"{operation_key} request schema surface",
        )

    runtime_success = sorted(
        code for code in runtime_operation["responses"] if str(code).startswith("2")
    )
    canonical_success = sorted(
        code for code in canonical_operation["responses"] if str(code).startswith("2")
    )
    _require(runtime_success == canonical_success, f"{operation_key} success status")
    for code in canonical_success:
        runtime_schema = _json_schema(runtime, runtime_operation["responses"][code])
        canonical_schema = _json_schema(
            canonical, canonical_operation["responses"][code]
        )
        _require(
            _surface_matches(
                _schema_surface(runtime, runtime_schema),
                _schema_surface(canonical, canonical_schema),
            ),
            f"{operation_key} response {code} schema surface",
        )


def _assert_error_envelopes(canonical: dict[str, Any]) -> None:
    for key, operation in _operations(canonical).items():
        for code, response in operation["responses"].items():
            if not str(code).startswith(("4", "5")):
                continue
            schema = _json_schema(canonical, _resolve(canonical, response))
            _, properties, required = _schema_surface(canonical, schema)
            _require(
                {"correlationId", "error"}.issubset(properties),
                f"{key} {code} error",
            )
            _require(
                {"correlationId", "error"}.issubset(required),
                f"{key} {code} error",
            )


def assert_openapi_conformance(runtime: dict[str, Any], canonical_path: Path) -> None:
    """Compare the runtime OpenAPI surface with its canonical provider contract."""
    canonical = yaml.safe_load(canonical_path.read_text(encoding="utf-8"))
    runtime_operations = _operations(runtime)
    canonical_operations = _operations(canonical)
    _require(
        set(runtime_operations) == set(canonical_operations), "path/method mismatch"
    )
    for key, expected in canonical_operations.items():
        actual = runtime_operations[key]
        _require(
            actual.get("operationId") == expected.get("operationId"),
            f"{key} operationId",
        )
        _require(
            _required_headers(runtime, key[0], actual)
            == _required_headers(canonical, key[0], expected),
            f"{key} required headers",
        )
        _require(
            _effective_security(runtime, actual)
            == _effective_security(canonical, expected),
            f"{key} security",
        )
        _assert_payload_surface(runtime, canonical, key)
    _assert_error_envelopes(canonical)


def make_service_jwt_settings(audience: str) -> ServiceJwtValidationSettings:
    """Create an isolated public key for provider OpenAPI tests."""
    import base64

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return ServiceJwtValidationSettings(
        public_key_path=None,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
        issuer="test-internal",
        audience=audience,
        allowed_subjects=frozenset({"booking-orchestrator"}),
    )


__all__ = ["assert_openapi_conformance", "make_service_jwt_settings"]
