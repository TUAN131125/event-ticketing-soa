#!/usr/bin/env python3
"""Offline semantic validator for the canonical contract catalog."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from check_manifest import validate_manifest
from contract_utils import (
    CONTRACTS,
    ContractError,
    find_placeholders,
    operations,
    read_json,
    read_yaml,
    resolve_ref,
    walk_refs,
)

EXPECTED: dict[str, set[tuple[str, str]]] = {
    "customer-service.yaml": {
        ("POST", "/customers"), ("GET", "/customers/{customerId}"), ("GET", "/customers:lookup"),
        ("PUT", "/customers/{customerId}"), ("POST", "/customers/{customerId}/consents"),
        ("POST", "/customers/{customerId}/deactivate"),
    },
    "event-service.yaml": {
        ("GET", "/events"), ("GET", "/events/{eventId}"), ("POST", "/events"),
        ("PUT", "/events/{eventId}"), ("POST", "/events/{eventId}/publish"),
        ("POST", "/events/{eventId}/pause"), ("POST", "/events/{eventId}/cancel"),
        ("GET", "/events/{eventId}/sale-eligibility"),
    },
    "booking-service.yaml": {
        ("POST", "/bookings"), ("GET", "/bookings/{bookingId}"),
        ("GET", "/customers/{customerId}/bookings"),
        ("POST", "/bookings/{bookingId}/reservation"),
        ("POST", "/bookings/{bookingId}/payment-started"),
        ("POST", "/bookings/{bookingId}/payment-result"),
        ("POST", "/bookings/{bookingId}/tickets"),
        ("POST", "/bookings/{bookingId}/confirm"), ("POST", "/bookings/{bookingId}/fail"),
        ("POST", "/bookings/{bookingId}/cancel"),
    },
    "payment-service.yaml": {
        ("POST", "/payments"), ("GET", "/payments/{paymentId}"),
        ("POST", "/payments/{paymentId}/authorize"), ("POST", "/payments/{paymentId}/capture"),
        ("POST", "/payments/{paymentId}/cancel"), ("POST", "/payments/{paymentId}/refunds"),
        ("POST", "/payments/provider-callback"), ("POST", "/payments/{paymentId}/reconcile"),
    },
    "ticket-service.yaml": {
        ("POST", "/tickets:issue"), ("GET", "/tickets/{ticketId}"),
        ("GET", "/bookings/{bookingId}/tickets"), ("POST", "/tickets/validate"),
        ("POST", "/tickets/{ticketId}/check-in"), ("POST", "/tickets/{ticketId}/cancel"),
        ("POST", "/tickets/{ticketId}/reissue-qr"),
    },
    "notification-service.yaml": {
        ("POST", "/webhooks/events"), ("GET", "/deliveries"), ("GET", "/deliveries/{deliveryId}"),
        ("POST", "/deliveries/{deliveryId}/retry"), ("PUT", "/templates/{code}"),
    },
    "esb-public-api.yaml": {
        ("GET", "/api/events"), ("GET", "/api/events/{eventId}"), ("POST", "/api/bookings"),
        ("GET", "/api/bookings/{bookingId}"), ("POST", "/api/bookings/{bookingId}/cancel"),
        ("GET", "/api/health"), ("GET", "/api/traces/{correlationId}"),
    },
    "realtime-service.yaml": set(),
    "identity-service.yaml": {
        ("POST", "/auth/register"), ("POST", "/auth/login"),
        ("POST", "/auth/refresh"), ("POST", "/auth/logout"),
        ("GET", "/auth/me"), ("POST", "/admin/users/{userId}/roles"),
        ("GET", "/.well-known/jwks.json"),
    },
}

EXPECTED_INTERNAL: dict[str, set[tuple[str, str]]] = {
    "customer-service.yaml": {
        ("PUT", "/internal/customers/{customerId}/identity-link"),
        ("DELETE", "/internal/customers/{customerId}/identity-link"),
        ("GET", "/internal/identity-mappings/{identitySubject}"),
    },
    "booking-service.yaml": {
        ("POST", "/internal/bookings/{bookingId}/access-decisions"),
    },
    "realtime-service.yaml": {
        ("POST", "/internal/status-events"),
        ("GET", "/connections/health"),
    },
}

EXPECTED_ADDITIONAL_PUBLIC = {
    "esb-public-api.yaml": {("POST", "/api/realtime/ws-tickets")},
}

EXPECTED_ENUMS = {
    ("event-service.yaml", "Event", "status"): {"DRAFT", "ON_SALE", "PAUSED", "CANCELLED", "ENDED"},
    ("booking-service.yaml", "Booking", "status"): {
        "PENDING", "SEAT_RESERVED", "PAYMENT_PROCESSING", "CONFIRMED",
        "FAILED", "CANCELLED", "COMPENSATION_PENDING",
    },
    ("payment-service.yaml", "Payment", "status"): {
        "CREATED", "AUTHORIZED", "CAPTURED", "FAILED", "CANCELLED",
        "UNKNOWN", "PARTIALLY_REFUNDED", "REFUNDED",
    },
    ("ticket-service.yaml", "Ticket", "status"): {"ISSUED", "CHECKED_IN", "CANCELLED"},
    ("notification-service.yaml", "Delivery", "status"): {
        "PENDING", "SENDING", "DELIVERED", "RETRY_PENDING", "DEAD_LETTER", "CANCELLED",
    },
}


class Result:
    def __init__(self) -> None:
        self.errors: list[ContractError] = []
        self.warnings: list[str] = []
        self.counts: dict[str, int] = {}

    def error(self, file: Path | str, rule: str, message: str) -> None:
        self.errors.append(ContractError(file, rule, message))

    def guard(self, file: Path | str, rule: str, callback: Any) -> Any:
        try:
            return callback()
        except (ContractError, KeyError, TypeError, ValueError, OSError) as exc:
            self.error(file, rule, str(exc))
            return None


def response_has_error_schema(response: Any, document: dict[str, Any], source: Path) -> bool:
    if not isinstance(response, dict):
        return False
    if "$ref" in response:
        try:
            response, _, _ = resolve_ref(response["$ref"], document, source)
        except (ContractError, KeyError):
            return False
    text = json.dumps(response, ensure_ascii=True)
    return "ErrorResponse" in text or "error-response.schema.json" in text


def validate_openapi(result: Result) -> None:
    openapi_dir = CONTRACTS / "openapi"
    operation_ids: dict[str, str] = {}
    common_ref_counts: Counter[str] = Counter()
    for filename, expected in EXPECTED.items():
        path = openapi_dir / filename
        document = result.guard(path, "openapi.parse", lambda: read_yaml(path))
        if not isinstance(document, dict):
            continue
        if document.get("openapi") != "3.1.0":
            result.error(path, "openapi.version", "openapi must equal 3.1.0")
        info = document.get("info", {})
        for field, value in {
            "version": "1.0.0",
            "x-contract-status": "canonical-v1",
            "x-designed-baseline-version": "1.0.0",
        }.items():
            if info.get(field) != value:
                result.error(path, "openapi.metadata", f"info.{field} must equal {value}")
        if "x-publication-decision" in info:
            result.error(path, "openapi.metadata", "x-publication-decision is forbidden in canonical v1")

        actual_operations = operations(document)
        additional_expected = EXPECTED_ADDITIONAL_PUBLIC.get(filename, set())
        internal_expected = EXPECTED_INTERNAL.get(filename, set())
        designed = {
            (method, route)
            for method, route, operation in actual_operations
            if operation.get("x-interface-class") != "internal"
            and not route.startswith("/health/")
            and route != "/metrics"
            and (method, route) not in additional_expected
        }
        internal = {
            (method, route)
            for method, route, operation in actual_operations
            if operation.get("x-interface-class") == "internal"
        }
        additional_public = {
            (method, route)
            for method, route, operation in actual_operations
            if (method, route) in additional_expected and operation.get("x-interface-class") == "public"
        }
        operational = {
            (method, route)
            for method, route, operation in actual_operations
            if ((route.startswith("/health/") or route == "/metrics" or operation.get("x-interface-class") == "operational")
                and (method, route) not in expected)
        }
        if designed != expected:
            result.error(path, "baseline.operations", f"expected {sorted(expected)}, got {sorted(designed)}")
        if internal != internal_expected:
            result.error(path, "internal.operations", f"expected {sorted(internal_expected)}, got {sorted(internal)}")
        if additional_public != additional_expected:
            result.error(path, "public.additional", f"expected {sorted(additional_expected)}, got {sorted(additional_public)}")
        result.counts[filename] = len(expected)
        result.counts[f"{filename}:internal"] = len(internal_expected)
        result.counts[f"{filename}:additionalPublic"] = len(additional_expected)
        result.counts[f"{filename}:operational"] = len(operational)

        for method, route, operation in actual_operations:
            operation_id = operation.get("operationId")
            if not operation_id:
                result.error(path, "openapi.operation-id", f"{method} {route} has no operationId")
            elif operation_id in operation_ids:
                result.error(path, "openapi.operation-id", f"duplicate {operation_id} also in {operation_ids[operation_id]}")
            else:
                operation_ids[operation_id] = f"{filename}:{method} {route}"
            responses = operation.get("responses")
            if not isinstance(responses, dict) or not responses:
                result.error(path, "openapi.responses", f"{method} {route} has no responses")
            else:
                for status, response in responses.items():
                    if str(status).startswith(("4", "5")) and not response_has_error_schema(response, document, path):
                        result.error(path, "openapi.error-envelope", f"{method} {route} response {status} is not ErrorResponse")
            if operation.get("x-interface-class") != "operational" and not route.startswith("/health/"):
                declared = "security" in operation or "security" in document
                if not declared:
                    result.error(path, "openapi.security", f"{method} {route} has no security declaration")

        for ref in walk_refs(document):
            result.guard(path, "openapi.ref", lambda ref=ref: resolve_ref(ref, document, path))

        schemas = document.get("components", {}).get("schemas", {})
        expected_common = {
            "ErrorResponse": "../common/error-response.schema.json",
            "Money": "../common/money.schema.json",
            "PageMeta": "../common/pagination.schema.json",
        }
        if "ErrorDetail" in schemas:
            result.error(path, "common.error-single-source", "ErrorDetail must not be independently authored")
        for schema_name, canonical_ref in expected_common.items():
            if schema_name in schemas:
                if schemas[schema_name] != {"$ref": canonical_ref}:
                    result.error(
                        path,
                        f"common.{schema_name.lower()}-single-source",
                        f"components.schemas.{schema_name} must be exactly $ref {canonical_ref}",
                    )
                else:
                    common_ref_counts[schema_name] += 1

        if filename == "realtime-service.yaml":
            realtime_operational = [
                (method, route)
                for method, route, operation in actual_operations
                if operation.get("x-interface-class") == "operational"
                or route.startswith("/health/") or route == "/metrics"
            ]
            expected_operational: set[tuple[str, str]] = set()
            if set(realtime_operational) != expected_operational:
                result.error(path, "realtime.operational", f"expected {sorted(expected_operational)}, got {sorted(realtime_operational)}")
            result.counts["realtimeOperational"] = len(realtime_operational)
            for method, route, operation in actual_operations:
                if (method, route) in internal_expected and operation.get("x-interface-class") != "internal":
                    result.error(path, "realtime.interface-class", f"{method} {route} must be internal")

    result.counts["commonErrorRefs"] = common_ref_counts["ErrorResponse"]
    result.counts["commonMoneyRefs"] = common_ref_counts["Money"]
    result.counts["commonPaginationRefs"] = common_ref_counts["PageMeta"]

    for (filename, schema_name, property_name), expected in EXPECTED_ENUMS.items():
        path = openapi_dir / filename
        document = read_yaml(path)
        actual = set(document["components"]["schemas"][schema_name]["properties"][property_name].get("enum", []))
        if actual != expected:
            result.error(path, "baseline.enum", f"{schema_name}.{property_name}: expected {sorted(expected)}, got {sorted(actual)}")

    validate_security_model(result)

    for filename, route, required_headers, security_name in [
        ("notification-service.yaml", "/webhooks/events", {"X-Webhook-Timestamp", "X-Webhook-Signature"}, "webhookHmac"),
        ("payment-service.yaml", "/payments/provider-callback", {"X-Provider-Timestamp", "X-Provider-Signature"}, "providerHmac"),
    ]:
        document = read_yaml(openapi_dir / filename)
        operation = document["paths"][route]["post"]
        headers = {item.get("name") for item in operation.get("parameters", []) if item.get("in") == "header"}
        if not required_headers <= headers:
            result.error(openapi_dir / filename, "signed-ingress.headers", f"{route} missing {sorted(required_headers - headers)}")
        if {security_name: []} not in operation.get("security", []):
            result.error(openapi_dir / filename, "signed-ingress.security", f"{route} must use {security_name}")


def validate_security_model(result: Result) -> None:
    """Assert the MAP-001, RT-AUTH-001 and ID-001 semantic decisions."""
    openapi_dir = CONTRACTS / "openapi"
    security_path = CONTRACTS / "common/openapi-security.yaml"
    security_document = read_yaml(security_path)
    schemes = security_document.get("components", {}).get("securitySchemes", {})
    if set(schemes) != {"BrowserBearerAuth", "InternalServiceJwt"}:
        result.error(security_path, "auth.schemes", "canonical schemes must be BrowserBearerAuth and InternalServiceJwt")
    browser = schemes.get("BrowserBearerAuth", {})
    service = schemes.get("InternalServiceJwt", {})
    if browser.get("x-required-claims") != ["sub", "roles", "tokenVersion", "iss", "aud", "iat", "exp"]:
        result.error(security_path, "auth.browser-claims", "BrowserBearerAuth required claims drifted")
    if browser.get("x-customer-id-authoritative") is not False:
        result.error(security_path, "auth.customer-id", "customerId must never be authoritative in a browser JWT")
    if set(service.get("x-required-claims", [])) != {"iss", "sub", "aud", "iat", "exp", "jti"}:
        result.error(security_path, "auth.service-claims", "InternalServiceJwt must require iss/sub/aud/iat/exp/jti")
    for field, expected in {
        "x-short-lived": True,
        "x-audience-bound": True,
        "x-caller-allow-list-required": True,
        "x-jti-replay-protection": "required",
        "x-browser-jwt-accepted": False,
    }.items():
        if service.get(field) != expected:
            result.error(security_path, "auth.service-policy", f"InternalServiceJwt.{field} must equal {expected!r}")

    customer_path = openapi_dir / "customer-service.yaml"
    customer = read_yaml(customer_path)
    mapping_operations = [
        customer["paths"]["/internal/customers/{customerId}/identity-link"]["put"],
        customer["paths"]["/internal/customers/{customerId}/identity-link"]["delete"],
        customer["paths"]["/internal/identity-mappings/{identitySubject}"]["get"],
    ]
    for operation in mapping_operations:
        if {"InternalServiceJwt": []} not in operation.get("security", []):
            result.error(customer_path, "mapping.security", "all identity mapping operations must use InternalServiceJwt")
        if operation.get("x-interface-class") != "internal" or operation.get("x-version") != "v1":
            result.error(customer_path, "mapping.class", "mapping operations must be internal v1")
    public_mapping_paths = [
        route for route in customer.get("paths", {})
        if ("identity" in route or "mapping" in route) and not route.startswith("/internal/")
    ]
    if public_mapping_paths:
        result.error(customer_path, "mapping.public", f"public mapping paths are forbidden: {public_mapping_paths}")
    mapping = customer["components"]["schemas"]["IdentityMapping"]
    if set(mapping["properties"]["status"].get("enum", [])) != {"ACTIVE", "INACTIVE", "UNLINKED"}:
        result.error(customer_path, "mapping.status", "mapping statuses must be ACTIVE/INACTIVE/UNLINKED")
    if set(mapping.get("properties", {})) & {"email", "phone", "name", "profile"}:
        result.error(customer_path, "mapping.pii", "IdentityMapping must not return profile or contact PII")
    link_parameters = json.dumps(mapping_operations[0].get("parameters", []))
    unlink_parameters = json.dumps(mapping_operations[1].get("parameters", []))
    if "IdempotencyKey" not in link_parameters or "IfMatch" not in unlink_parameters:
        result.error(customer_path, "mapping.concurrency", "link requires Idempotency-Key and unlink requires If-Match")

    booking_path = openapi_dir / "booking-service.yaml"
    booking = read_yaml(booking_path)
    decision_operation = booking["paths"]["/internal/bookings/{bookingId}/access-decisions"]["post"]
    if {"InternalServiceJwt": []} not in decision_operation.get("security", []):
        result.error(booking_path, "access.security", "Booking access decision must use InternalServiceJwt")
    expected_invariants = {
        "x-interface-class": "internal",
        "x-version": "v1",
        "x-allowed-callers": ["booking-orchestrator"],
        "x-end-user-context-source": "verified-browser-jwt",
        "x-role-assertion-policy": "caller-must-not-elevate",
        "x-failure-policy": "deny",
    }
    for field, expected in expected_invariants.items():
        if decision_operation.get(field) != expected:
            result.error(booking_path, "access.invariant", f"{field} must equal {expected!r}")
    if decision_operation.get("x-cache-max-age-seconds", 999) > 5:
        result.error(booking_path, "access.cache", "access decision cache maximum must be no more than five seconds")
    decision_schema = booking["components"]["schemas"]["BookingAccessDecision"]
    expected_reasons = {
        "OWNER", "ADMIN_OVERRIDE", "BOOKING_NOT_FOUND", "IDENTITY_NOT_MAPPED",
        "CUSTOMER_INACTIVE", "NOT_OWNER", "DEPENDENCY_UNAVAILABLE",
    }
    if set(decision_schema["properties"]["reasonCode"].get("enum", [])) != expected_reasons:
        result.error(booking_path, "access.reasons", "Booking access reason codes drifted")
    decision_text = json.dumps(decision_operation, ensure_ascii=False).lower()
    if "admin is the only role" not in decision_text or "allowed=false" not in decision_text:
        result.error(booking_path, "access.fail-closed", "decision must declare ADMIN-only override and fail-closed denial")

    esb_path = openapi_dir / "esb-public-api.yaml"
    esb = read_yaml(esb_path)
    ticket_operation = esb["paths"]["/api/realtime/ws-tickets"]["post"]
    if {"BrowserBearerAuth": []} not in ticket_operation.get("security", []):
        result.error(esb_path, "ticket.security", "WS ticket issuance must use BrowserBearerAuth")
    ticket_request = esb["components"]["schemas"]["WsTicketRequest"]
    if set(ticket_request.get("properties", {})) != {"bookingId"}:
        result.error(esb_path, "ticket.request", "WS ticket request must contain bookingId only")
    policy = esb["components"]["schemas"]["WsTicketPolicy"]["properties"]
    expected_policy = {
        "maximumTtlSeconds": 60,
        "singleUse": True,
        "jtiRequired": True,
        "refreshable": False,
        "bookingBound": True,
        "identitySubjectBound": True,
        "signed": True,
        "issuer": "booking-orchestrator",
        "scope": "booking:status:read",
    }
    for name, expected in expected_policy.items():
        if policy.get(name, {}).get("const") != expected:
            result.error(esb_path, "ticket.policy", f"WsTicketPolicy.{name} must equal {expected!r}")
    ticket_claims = esb["components"]["schemas"]["SignedWebSocketTicketClaims"]
    required_ticket_claims = {"iss", "aud", "sub", "bookingId", "scope", "iat", "exp", "jti"}
    if set(ticket_claims.get("required", [])) != required_ticket_claims:
        result.error(esb_path, "ticket.claims", "signed WS ticket required claims drifted")
    policy_claims = set(policy.get("requiredClaims", {}).get("const", []))
    if policy_claims != required_ticket_claims:
        result.error(esb_path, "ticket.policy", "ticket policy requiredClaims drifted")

    identity_path = openapi_dir / "identity-service.yaml"
    identity = read_yaml(identity_path)
    claims = identity["components"]["schemas"]["AccessTokenClaims"]
    if "customerId" in claims.get("properties", {}) or "customerId" in claims.get("required", []):
        result.error(identity_path, "identity.customer-id", "Identity JWT must not define authoritative customerId")
    if any("identity-mapping" in route or "identity-link" in route for route in identity.get("paths", {})):
        result.error(identity_path, "identity.mapping", "Identity Service must not expose mapping operations")

    realtime_path = openapi_dir / "realtime-service.yaml"
    realtime = read_yaml(realtime_path)
    ingestion = realtime["paths"]["/internal/status-events"]["post"]
    if {"InternalServiceJwt": []} not in ingestion.get("security", []):
        result.error(realtime_path, "realtime.service-auth", "status ingestion must use InternalServiceJwt")
    policy = ingestion.get("x-service-jwt-policy", {})
    if set(policy.get("requiredClaims", [])) != {"iss", "sub", "aud", "iat", "exp", "jti"}:
        result.error(realtime_path, "realtime.service-claims", "status ingestion service JWT claims drifted")
    if policy.get("audience") != "realtime-status-service" or policy.get("replayedJtiRejected") is not True:
        result.error(realtime_path, "realtime.service-policy", "status ingestion must be audience-bound and replay protected")

    client_path = CONTRACTS / "websocket/realtime-status/client-message.schema.json"
    client = read_json(client_path)
    frame_types = {variant.get("properties", {}).get("type", {}).get("const") for variant in client.get("oneOf", [])}
    if not {"authenticate", "subscribe", "unsubscribe"} <= frame_types:
        result.error(client_path, "websocket.frames", "client schema must support authenticate/subscribe/unsubscribe")
    protocol_path = CONTRACTS / "websocket/realtime-status/protocol.md"
    protocol = protocol_path.read_text(encoding="utf-8").lower()
    required_protocol_terms = [
        "connected_unauthenticated", "authenticated", "subscribed", "within five seconds",
        "query string", "forbidden", "signed", "single-use", "60 seconds",
        "verifies signature", "issuer, audience", "atomically consumes", "exactly once",
    ]
    missing_terms = [term for term in required_protocol_terms if term not in protocol]
    if missing_terms:
        result.error(protocol_path, "websocket.protocol", f"missing required authentication semantics: {missing_terms}")
    close_path = CONTRACTS / "websocket/realtime-status/close-codes.yaml"
    close_items = read_yaml(close_path).get("codes", [])
    close_codes = {item["code"]: item["name"] for item in close_items}
    close_standard = {item["code"]: item.get("standard", False) for item in close_items}
    expected_codes = {
        1001: "GOING_AWAY", 1012: "SERVICE_RESTART",
        4401: "AUTHENTICATION_REQUIRED", 4403: "ACCESS_DENIED",
        4408: "AUTHENTICATION_TIMEOUT", 4410: "HEARTBEAT_TIMEOUT",
        4429: "CONNECTION_LIMIT",
    }
    for code, name in expected_codes.items():
        if close_codes.get(code) != name:
            result.error(close_path, "websocket.close-code", f"{code} must be {name}")
    for code in (1001, 1012):
        if close_standard.get(code) is not True:
            result.error(close_path, "websocket.standard-code", f"{code} must remain a standard close code")


def validate_json_schemas(result: Result) -> None:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        from jsonschema.exceptions import SchemaError
        from referencing import Registry, Resource
        from referencing.exceptions import Unresolvable
        from referencing.jsonschema import DRAFT202012
    except ImportError as exc:
        result.error(
            "scripts/validate_contracts.py",
            "schema.engine",
            f"jsonschema and referencing are required for Draft 2020-12 validation: {exc}",
        )
        return

    schema_paths = sorted(
        set(CONTRACTS.glob("common/*.schema.json"))
        | set(CONTRACTS.glob("events/**/*.schema.json"))
        | set(CONTRACTS.glob("webhooks/**/*.schema.json"))
        | set(CONTRACTS.glob("websocket/**/*.schema.json"))
    )
    example_count = 0
    ref_count = 0
    registry = Registry()
    documents: dict[Path, dict[str, Any]] = {}
    identifiers: dict[str, Path] = {}
    for path in schema_paths:
        document = result.guard(path, "schema.parse", lambda path=path: read_json(path))
        if not isinstance(document, dict):
            continue
        documents[path] = document
        if document.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            result.error(path, "schema.dialect", "must declare Draft 2020-12")
        if document.get("x-contract-status") != "canonical-v1":
            result.error(path, "schema.status", "x-contract-status must equal canonical-v1")
        if document.get("x-designed-baseline-version") != "1.0.0":
            result.error(path, "schema.version", "x-designed-baseline-version must equal 1.0.0")
        if "x-publication-decision" in document:
            result.error(path, "schema.metadata", "x-publication-decision is forbidden in canonical v1")
        schema_id = document.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            result.error(path, "schema.id", "manifest JSON Schema artifacts require a non-empty canonical $id")
            continue
        if schema_id in identifiers:
            result.error(path, "schema.id-duplicate", f"$id {schema_id} is also used by {identifiers[schema_id]}")
            continue
        identifiers[schema_id] = path
        try:
            Draft202012Validator.check_schema(document)
            resource = Resource.from_contents(document)
            registry = registry.with_resource(schema_id, resource)
            registry = registry.with_resource(path.resolve().as_uri(), resource)
        except (SchemaError, ValueError) as exc:
            result.error(path, "schema.meta", str(exc))

    format_checker = FormatChecker()
    for path, document in documents.items():
        schema_id = document.get("$id")
        if not isinstance(schema_id, str) or schema_id not in identifiers:
            continue
        resolver = registry.resolver(base_uri=schema_id)
        for ref in walk_refs(document):
            ref_count += 1
            try:
                resolver.lookup(ref)
            except Unresolvable as exc:
                result.error(path, "schema.ref", f"cannot resolve {ref}: {exc}")
        validator = Draft202012Validator(document, registry=registry, format_checker=format_checker)
        for index, example in enumerate(document.get("examples", [])):
            for validation_error in validator.iter_errors(example):
                result.error(path, "schema.example", f"examples[{index}] {validation_error.json_path}: {validation_error.message}")
            example_count += 1
        for index, example in enumerate(document.get("x-invalidExamples", [])):
            errors = list(validator.iter_errors(example))
            if not errors:
                result.error(
                    path,
                    "schema.invalid-example",
                    f"x-invalidExamples[{index}] unexpectedly validates",
                )
            example_count += 1

    event_envelope = read_json(CONTRACTS / "common/event-envelope.schema.json")
    required = {"eventId", "eventType", "schemaVersion", "occurredAt", "correlationId", "aggregateId", "data"}
    if set(event_envelope.get("required", [])) != required:
        result.error("common/event-envelope.schema.json", "event.envelope", f"required fields must be {sorted(required)}")
    error_schema = read_json(CONTRACTS / "common/error-response.schema.json")
    detail_required = set(error_schema["properties"]["error"]["required"])
    if detail_required != {"code", "message", "retryable"}:
        result.error("common/error-response.schema.json", "error.required", "error must require code/message/retryable; details is optional")

    status_schema = read_json(CONTRACTS / "websocket/realtime-status/status-message.schema.json")
    status_required = {"messageId", "bookingId", "status", "sequence", "occurredAt", "correlationId"}
    if set(status_schema.get("required", [])) != status_required:
        result.error("websocket/realtime-status/status-message.schema.json", "realtime.required", "status fields differ from Phase-5 schema")
    expected_status = EXPECTED_ENUMS[("booking-service.yaml", "Booking", "status")]
    if set(status_schema["properties"]["status"]["enum"]) != expected_status:
        result.error("websocket/realtime-status/status-message.schema.json", "realtime.status", "status enum must match Booking baseline")

    index_path = CONTRACTS / "examples/http/index.json"
    index = read_json(index_path)
    openapi_resources: dict[Path, Any] = {}
    for item in index:
        example_path = index_path.parent / item["file"]
        instance = read_json(example_path)
        if "openapi" in item:
            source = CONTRACTS / "openapi" / item["openapi"]
            document = read_yaml(source)
            if source not in openapi_resources:
                resource = Resource(contents=document, specification=DRAFT202012)
                registry = registry.with_resource(source.resolve().as_uri(), resource)
                openapi_resources[source] = resource
            schema = {"$ref": f"{source.resolve().as_uri()}#/components/schemas/{item['schema']}"}
        else:
            source = (index_path.parent / item["jsonSchema"]).resolve()
            schema = read_json(source)
        validator = Draft202012Validator(schema, registry=registry, format_checker=format_checker)
        for validation_error in validator.iter_errors(instance):
            result.error(example_path, "example.http", f"{validation_error.json_path}: {validation_error.message}")
        example_count += 1

    for example_path in sorted((CONTRACTS / "examples/events").glob("*.json")):
        instance = read_json(example_path)
        event_type = instance.get("eventType")
        candidates = [path for path in CONTRACTS.glob("events/**/*.schema.json") if read_json(path).get("title") == event_type]
        if len(candidates) != 1:
            result.error(example_path, "example.event-map", f"expected one schema for {event_type}, found {len(candidates)}")
            continue
        schema_path = candidates[0]
        schema = read_json(schema_path)
        validator = Draft202012Validator(schema, registry=registry, format_checker=format_checker)
        for validation_error in validator.iter_errors(instance):
            result.error(example_path, "example.event", f"{validation_error.json_path}: {validation_error.message}")
        example_count += 1

    external_examples = [
        ("examples/webhooks/notification-booking-confirmed.json", "webhooks/notification/notification-webhook.schema.json"),
        ("examples/websocket/status.json", "websocket/realtime-status/status-message.schema.json"),
        ("examples/websocket/resync-required.json", "websocket/realtime-status/server-control-message.schema.json"),
        ("examples/websocket/authenticate.json", "websocket/realtime-status/client-message.schema.json"),
        ("examples/websocket/authenticated.json", "websocket/realtime-status/server-control-message.schema.json"),
        ("examples/websocket/ticket-expired.json", "websocket/realtime-status/server-control-message.schema.json"),
        ("examples/websocket/ticket-reused.json", "websocket/realtime-status/server-control-message.schema.json"),
    ]
    for example_relative, schema_relative in external_examples:
        example_path = CONTRACTS / example_relative
        schema_path = CONTRACTS / schema_relative
        instance, schema = read_json(example_path), read_json(schema_path)
        validator = Draft202012Validator(schema, registry=registry, format_checker=format_checker)
        for validation_error in validator.iter_errors(instance):
            result.error(example_path, "example.external", f"{validation_error.json_path}: {validation_error.message}")
        example_count += 1
    result.counts["jsonSchemas"] = len(schema_paths)
    result.counts["schemaIds"] = len(identifiers)
    result.counts["schemaRefs"] = ref_count
    result.counts["examples"] = example_count


def import_lxml() -> Any:
    try:
        from lxml import etree
        return etree
    except ImportError:
        runtime_root = Path.home() / ".cache" / "codex-runtimes"
        for site_packages in runtime_root.glob("*/dependencies/python/Lib/site-packages"):
            sys.path.insert(0, str(site_packages))
            try:
                from lxml import etree
                return etree
            except ImportError:
                continue
    raise ImportError("lxml is unavailable; XSD compilation cannot run")


def delegate_to_bundled_runtime() -> int | None:
    """Use bundled Python 3.12 when the caller lacks a required validation engine."""
    try:
        import_lxml()
        import jsonschema  # noqa: F401
        import referencing  # noqa: F401
        return None
    except ImportError:
        runtime = (
            Path.home()
            / ".cache"
            / "codex-runtimes"
            / "codex-primary-runtime"
            / "dependencies"
            / "python"
            / "python.exe"
        )
        if not runtime.is_file() or runtime.resolve() == Path(sys.executable).resolve():
            return None
        env = os.environ.copy()
        import_paths = [
            item
            for item in sys.path
            if item and Path(item).exists() and Path(item).name == "site-packages"
        ]
        existing = env.get("PYTHONPATH")
        if existing:
            import_paths.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(import_paths)
        completed = subprocess.run([str(runtime), str(Path(__file__).resolve())], env=env, check=False)
        return completed.returncode


def validate_soap(result: Result) -> None:
    try:
        etree = import_lxml()
    except ImportError as exc:
        result.error("soap/seat-inventory.xsd", "soap.xsd-tool", str(exc))
        return
    xsd_path = CONTRACTS / "soap/seat-inventory.xsd"
    wsdl_path = CONTRACTS / "soap/seat-inventory.wsdl"
    try:
        xsd_document = etree.parse(str(xsd_path))
        schema = etree.XMLSchema(xsd_document)
        wsdl_document = etree.parse(str(wsdl_path))
    except (OSError, etree.XMLSyntaxError, etree.XMLSchemaParseError) as exc:
        result.error(xsd_path, "soap.compile", str(exc))
        return
    root = wsdl_document.getroot()
    namespace = "urn:event-ticketing:seat:v1"
    if root.get("targetNamespace") != namespace:
        result.error(wsdl_path, "soap.namespace", f"targetNamespace must be {namespace}")
    ns = {"wsdl": "http://schemas.xmlsoap.org/wsdl/", "soap": "http://schemas.xmlsoap.org/wsdl/soap/"}
    operations_found = {
        node.get("name")
        for node in root.xpath("./wsdl:portType/wsdl:operation", namespaces=ns)
    }
    expected = {"GetSeatMap", "CheckAvailability", "ReserveSeats", "GetReservation", "ExtendReservation", "ConfirmSeats", "ReleaseSeats", "ExpireReservations"}
    if operations_found != expected:
        result.error(wsdl_path, "soap.operations", f"expected {sorted(expected)}, got {sorted(operations_found)}")
    actions = {
        node.getparent().get("name"): node.get("soapAction")
        for node in root.xpath("./wsdl:binding/wsdl:operation/soap:operation", namespaces=ns)
    }
    for operation in expected:
        if actions.get(operation) != f"{namespace}/{operation}":
            result.error(wsdl_path, "soap.action", f"{operation} action is {actions.get(operation)!r}")
    wsdl_text = wsdl_path.read_text(encoding="utf-8")
    if "SeatServiceFault" not in wsdl_text or "SeatInventoryFault" in wsdl_text:
        result.error(wsdl_path, "soap.fault", "fault must be SeatServiceFault only")

    soap_namespace = "http://schemas.xmlsoap.org/soap/envelope/"
    examples = sorted((CONTRACTS / "soap/examples").glob("*.xml"))
    request_names: set[str] = set()
    for example in examples:
        try:
            document = etree.parse(str(example))
            body = document.getroot().find(f"{{{soap_namespace}}}Body")
            if body is None or len(body) != 1:
                raise ValueError("SOAP Body must have one child")
            child = body[0]
            if child.tag == f"{{{soap_namespace}}}Fault":
                nodes = child.xpath(".//*[local-name()='SeatServiceFault']")
                if len(nodes) != 1 or not schema.validate(nodes[0]):
                    raise ValueError(schema.error_log.last_error or "fault detail does not validate")
            else:
                request_names.add(etree.QName(child).localname)
                if not schema.validate(child):
                    raise ValueError(schema.error_log.last_error or "request does not validate")
        except (OSError, etree.XMLSyntaxError, ValueError) as exc:
            result.error(example, "soap.example", str(exc))
    expected_requests = {f"{name}Request" for name in expected}
    if request_names != expected_requests:
        result.error("soap/examples", "soap.example-coverage", f"expected {sorted(expected_requests)}, got {sorted(request_names)}")
    result.counts["soapOperations"] = len(expected)
    result.counts["soapExamples"] = len(examples)


def validate_cleanup(result: Result) -> None:
    forbidden_directories = {"rebuild", "reports", "release", "generated", "__pycache__"}
    for path in CONTRACTS.rglob("*"):
        if path.is_dir() and path.name in forbidden_directories:
            result.error(path, "cleanup.directory", f"forbidden catalog directory: {path.name}")
        if path.is_file() and path.suffix.lower() in {".pyc", ".pyo"}:
            result.error(path, "cleanup.cache", "compiled Python files are forbidden")
    forbidden_notification = [
        path for path in CONTRACTS.rglob("*")
        if path.is_file() and "notification.requested" in path.name.lower()
    ]
    for path in forbidden_notification:
        result.error(path, "cleanup.notification-event", "notification.requested is excluded from v1")

    forbidden_patterns = {
        "2.0.0": re.compile(r"2\.0\.0", re.IGNORECASE),
        "next-major-label": re.compile(r"\bv2\b", re.IGNORECASE),
        "compatibility-release": re.compile(r"compatibility-release", re.IGNORECASE),
        "legacyBaseline": re.compile(r"legacyBaseline", re.IGNORECASE),
        "architecture-evolution-pending": re.compile(r"architecture-evolution-pending", re.IGNORECASE),
        "architecture-evolution-candidate": re.compile(r"architecture-evolution-candidate", re.IGNORECASE),
        "design-derived-candidate": re.compile(r"design-derived-candidate", re.IGNORECASE),
        "reviewed-runtime-candidate": re.compile(r"reviewed-runtime-candidate", re.IGNORECASE),
        "candidate-approved-for-implementation": re.compile(r"candidate-approved-for-implementation", re.IGNORECASE),
        "DECISION_REQUIRED": re.compile(r"DECISION_REQUIRED", re.IGNORECASE),
        "PROJECT_DIRECTION_PENDING": re.compile(r"PROJECT_DIRECTION_PENDING", re.IGNORECASE),
        "Prompt-2B-not-ready": re.compile(r"Prompt 2B.*NOT_READY", re.IGNORECASE),
    }
    own_path = Path(__file__).resolve()
    for path in CONTRACTS.rglob("*"):
        if not path.is_file() or path.resolve() == own_path:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in forbidden_patterns.items():
            if pattern.search(text):
                result.error(path, "cleanup.text", f"forbidden catalog marker: {label}")

    decisions_path = CONTRACTS / "DECISIONS.md"
    decisions = decisions_path.read_text(encoding="utf-8") if decisions_path.is_file() else ""
    required_decisions = {
        "GOV-001", "GOV" + "-002", "MAP-001", "ID-001", "RT-AUTH-001", "NOTIFICATION-EVENT-001",
    }
    missing = sorted(code for code in required_decisions if code not in decisions)
    if missing:
        result.error(decisions_path, "decisions.required", f"missing closed decisions: {missing}")
    if "Prompt 2 status: **COMPLETE**" not in decisions:
        result.error(decisions_path, "decisions.complete", "Prompt 2 must be COMPLETE")
    governance_code = "GOV" + "-002"
    for path in CONTRACTS.rglob("*"):
        if not path.is_file() or path == decisions_path or path.resolve() == own_path:
            continue
        if governance_code in path.read_text(encoding="utf-8", errors="replace"):
            result.error(path, "cleanup.governance-marker", f"{governance_code} may appear only as a closed decision")
    result.counts["cleanupDirectories"] = sum(
        1 for path in CONTRACTS.rglob("*") if path.is_dir() and path.name in forbidden_directories
    )


def main() -> int:
    delegated = delegate_to_bundled_runtime()
    if delegated is not None:
        return delegated
    result = Result()
    manifest_errors, manifest = validate_manifest()
    result.errors.extend(manifest_errors)
    result.counts["manifestEntries"] = len(manifest.get("contracts", [])) if manifest else 0
    result.errors.extend(find_placeholders())
    cache_artifacts = [
        path
        for path in CONTRACTS.rglob("*")
        if (path.is_dir() and path.name == "__pycache__")
        or (path.is_file() and path.suffix.lower() in {".pyc", ".pyo"})
    ]
    result.counts["cacheArtifacts"] = len(cache_artifacts)
    validate_openapi(result)
    validate_json_schemas(result)
    validate_soap(result)
    validate_cleanup(result)

    for warning in result.warnings:
        print(f"WARNING {warning}")
    for error in result.errors:
        print(f"ERROR {error}")
    operation_summary = ", ".join(
        f"{name.removesuffix('-service.yaml').removesuffix('.yaml')}={result.counts.get(name, 0)}"
        for name in EXPECTED
    )
    print(f"PUBLIC_BUSINESS {operation_summary}, seat-soap={result.counts.get('soapOperations', 0)}")
    internal_summary = ", ".join(
        f"{name.removesuffix('-service.yaml').removesuffix('.yaml')}={result.counts.get(f'{name}:internal', 0)}"
        for name in EXPECTED_INTERNAL
    )
    print(f"INTERNAL {internal_summary}")
    additional_public_summary = ", ".join(
        f"{name.removesuffix('-service.yaml').removesuffix('.yaml')}={result.counts.get(f'{name}:additionalPublic', 0)}"
        for name in EXPECTED_ADDITIONAL_PUBLIC
    )
    print(f"ADDITIONAL_PUBLIC {additional_public_summary}")
    operational_summary = ", ".join(
        f"{name.removesuffix('-service.yaml').removesuffix('.yaml')}={result.counts.get(f'{name}:operational', 0)}"
        for name in EXPECTED
    )
    print(f"OPERATIONAL {operational_summary}")
    print(
        "ARTIFACTS "
        f"manifest={result.counts.get('manifestEntries', 0)} "
        f"jsonSchemas={result.counts.get('jsonSchemas', 0)} "
        f"examples={result.counts.get('examples', 0)} "
        f"soapExamples={result.counts.get('soapExamples', 0)}"
    )
    print(
        "JSON_SCHEMA "
        "engine=jsonschema.Draft202012Validator "
        f"registryIds={result.counts.get('schemaIds', 0)} "
        f"refs={result.counts.get('schemaRefs', 0)}"
    )
    print(
        "REALTIME "
        f"internal={result.counts.get('realtime-service.yaml:internal', 0)} "
        f"operational={result.counts.get('realtimeOperational', 0)}"
    )
    print(
        "COMMON_REFS "
        f"errorResponse={result.counts.get('commonErrorRefs', 0)} "
        f"money={result.counts.get('commonMoneyRefs', 0)} "
        f"pagination={result.counts.get('commonPaginationRefs', 0)}"
    )
    event_statuses = Counter(
        item.get("contractStatus")
        for item in manifest.get("contracts", [])
        if str(item.get("canonicalPath", "")).startswith("events/")
    ) if manifest else Counter()
    print("CONTRACT_STATUS " + " ".join(f"{status}={count}" for status, count in sorted(event_statuses.items())))
    print(
        f"CLEANUP directories={result.counts.get('cleanupDirectories', 0)} "
        f"cacheArtifacts={result.counts.get('cacheArtifacts', 0)}"
    )
    if result.errors:
        print(f"CONTRACT_VALIDATION FAIL errors={len(result.errors)} warnings={len(result.warnings)}")
        return 1
    print(f"CONTRACT_VALIDATION PASS errors=0 warnings={len(result.warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
