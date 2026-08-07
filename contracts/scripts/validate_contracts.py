"""Validate every canonical runtime contract without changing the repository."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from contract_utils import (
    CONTRACTS_ROOT,
    EXPECTED_ARTIFACTS,
    EXPECTED_PORTS,
    MANIFEST_PATH,
    Artifact,
    ContractError,
    json_pointer,
    load_manifest,
    manifest_artifacts,
    operations,
    read_json,
    read_yaml,
    walk_mappings,
    walk_refs,
)


OPENAPI_FORMAT = "openapi-3.1"
MUTATION_EXCLUSIONS = {
    "/auth/login",
    "/auth/refresh",
    "/auth/logout",
    "/webhooks/events",
    "/internal/status-events",
    "/internal/bookings/{bookingId}/access-decisions",
    # The ESB publishes the Identity session endpoints behind an /api prefix. A session
    # is established, not replayed, so the same exclusion applies to the façade.
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/logout",
    # Safe lookup expressed as POST so the QR token never appears in a URL, a path or a
    # log line. It creates nothing, so there is no command for a key to make repeatable.
    "/api/check-in/validate",
}
# A precondition operation must declare If-Match, but may declare it optional where the
# same operation can also create the resource and so has no prior version to match.
CORRELATION_PARAMETERS = ("CorrelationId", "RequiredCorrelationId")
PRECONDITION_PARAMETERS = ("IfMatch", "OptionalIfMatch")
# Operations whose concurrency token is not an HTTP header. Seat inventory is fronted by
# the SOAP Seat service: the expected version travels in the body as `inventoryVersion`
# and no ETag is ever issued for the resource, so an If-Match header would carry nothing.
PRECONDITION_EXCLUSIONS = {
    "/api/admin/events/{eventId}/seat-inventory",
}


@dataclass
class Report:
    errors: list[ContractError] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def error(self, file: Path | str, rule: str, message: str) -> None:
        self.errors.append(ContractError(file, rule, message))

    def capture(self, callback: Any, *args: Any) -> Any:
        try:
            return callback(*args)
        except ContractError as exc:
            self.errors.append(exc)
            return None


def require_validation_dependencies() -> tuple[Any, Any, Any]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        from lxml import etree
    except ImportError as exc:  # pragma: no cover - dependency diagnostic
        raise ContractError(
            "contracts/scripts/validate_contracts.py",
            "dependency",
            "PyYAML, jsonschema and lxml are required",
        ) from exc
    return Draft202012Validator, FormatChecker, etree


def validate_manifest(report: Report) -> list[Artifact]:
    manifest = report.capture(load_manifest)
    if manifest is None:
        return []
    if manifest.get("sourceOfTruth") != "contracts/":
        report.error(
            MANIFEST_PATH, "manifest.source", "sourceOfTruth must be contracts/"
        )
    management = set(manifest.get("managementFiles", []))
    expected_management = {
        "CONTRACT_STANDARD.md",
        "CONTRACT_REVIEW.md",
        "manifest.yaml",
    }
    if management != expected_management:
        report.error(
            MANIFEST_PATH,
            "manifest.management",
            f"expected {sorted(expected_management)}",
        )
    artifacts = report.capture(manifest_artifacts, manifest) or []
    actual_paths = {artifact.relative_path for artifact in artifacts}
    if actual_paths != EXPECTED_ARTIFACTS:
        report.error(
            MANIFEST_PATH,
            "manifest.artifacts",
            f"missing={sorted(EXPECTED_ARTIFACTS - actual_paths)} extra={sorted(actual_paths - EXPECTED_ARTIFACTS)}",
        )
    contract_ids = {artifact.contract_id for artifact in artifacts}
    expected_ids = set(EXPECTED_PORTS) | {"event-messages"}
    if contract_ids != expected_ids:
        report.error(
            MANIFEST_PATH, "manifest.contracts", f"expected {sorted(expected_ids)}"
        )
    for artifact in artifacts:
        if not artifact.path.is_file():
            report.error(
                artifact.path,
                "manifest.missing",
                "declared runtime artifact is missing",
            )
        expected_port = EXPECTED_PORTS.get(artifact.contract_id)
        if expected_port is not None and artifact.port != expected_port:
            report.error(
                MANIFEST_PATH,
                "manifest.port",
                f"{artifact.contract_id} must use port {expected_port}",
            )
    report.counts["runtimeArtifacts"] = len(artifacts)
    report.counts["runtimeContracts"] = len(contract_ids)
    return artifacts


def validate_catalog_shape(report: Report) -> None:
    forbidden_directories = [
        "common",
        "openapi",
        "soap",
        "events",
        "webhooks",
        "websocket",
    ]
    for name in forbidden_directories:
        path = CONTRACTS_ROOT / name
        if path.exists():
            report.error(
                path,
                "catalog.legacy-layout",
                "legacy runtime contract directory must be removed",
            )
    duplicates = [
        CONTRACTS_ROOT.parent
        / "services/identity-service/contracts/identity-service.yaml",
        CONTRACTS_ROOT.parent
        / "services/seat-inventory-service/contracts/seat-inventory.wsdl",
        CONTRACTS_ROOT.parent
        / "services/seat-inventory-service/contracts/seat-inventory.xsd",
    ]
    for path in duplicates:
        if path.exists():
            report.error(
                path,
                "catalog.duplicate",
                "service-local runtime contract duplicates the canonical root",
            )


def parameter_refs(operation: dict[str, Any]) -> set[str]:
    return {
        item["$ref"]
        for item in operation.get("parameters", [])
        if isinstance(item, dict) and isinstance(item.get("$ref"), str)
    }


def resolved_parameter_keys(
    document: dict[str, Any], operation: dict[str, Any]
) -> list[tuple[str, str]]:
    """Return the (name, in) wire identity of every parameter after $ref resolution."""
    keys: list[tuple[str, str]] = []
    for item in operation.get("parameters", []):
        if not isinstance(item, dict):
            continue
        target = item
        if isinstance(item.get("$ref"), str):
            try:
                target = json_pointer(document, item["$ref"])
            except (KeyError, IndexError, TypeError, ValueError):
                continue
        if not isinstance(target, dict):
            continue
        name = target.get("name")
        location = target.get("in")
        if isinstance(name, str) and isinstance(location, str):
            keys.append((name, location))
    return keys


def ref_cycles(document: dict[str, Any]) -> list[str]:
    """Return one message per local $ref cycle reachable from components."""
    components = document.get("components")
    if not isinstance(components, dict):
        return []
    edges: dict[str, set[str]] = {}
    for group, entries in components.items():
        if not isinstance(entries, dict):
            continue
        for name, node in entries.items():
            pointer = f"#/components/{group}/{name}"
            edges[pointer] = {
                ref for ref in walk_refs(node) if ref.startswith("#/components/")
            }
    messages: list[str] = []
    reported: set[frozenset[str]] = set()
    visiting: list[str] = []
    state: dict[str, int] = {}

    def visit(node: str) -> None:
        if state.get(node) == 2:
            return
        if state.get(node) == 1:
            cycle = visiting[visiting.index(node) :] + [node]
            signature = frozenset(cycle)
            if signature not in reported:
                reported.add(signature)
                messages.append(" -> ".join(cycle))
            return
        state[node] = 1
        visiting.append(node)
        for target in sorted(edges.get(node, ())):
            visit(target)
        visiting.pop()
        state[node] = 2

    for node in sorted(edges):
        visit(node)
    return messages


def validate_openapi_components(
    report: Report, path: Path, document: dict[str, Any]
) -> None:
    components = document.get("components", {})
    schemes = components.get("securitySchemes", {})
    expected_schemes = {"UserJwt", "ServiceJwt", "WebhookHmac"}
    if not expected_schemes.issubset(schemes):
        report.error(
            path,
            "openapi.security-schemes",
            f"missing {sorted(expected_schemes - set(schemes))}",
        )
    parameters = components.get("parameters", {})
    expected_headers = {
        "CorrelationId": "X-Correlation-ID",
        "Traceparent": "traceparent",
        "IdempotencyKey": "Idempotency-Key",
        "IfMatch": "If-Match",
    }
    for key, wire_name in expected_headers.items():
        if parameters.get(key, {}).get("name") != wire_name:
            report.error(path, "openapi.parameters", f"{key} must declare {wire_name}")
    if "ETag" not in components.get("headers", {}):
        report.error(path, "openapi.etag", "components.headers.ETag is required")
    schemas = components.get("schemas", {})
    error = schemas.get("ErrorResponse", {})
    if set(error.get("required", [])) != {"correlationId", "error"}:
        report.error(
            path, "openapi.error", "ErrorResponse must require correlationId and error"
        )
    detail = error.get("properties", {}).get("error", {})
    if set(detail.get("required", [])) != {"code", "message", "retryable"}:
        report.error(
            path,
            "openapi.error-detail",
            "error must require code, message and retryable",
        )
    money = schemas.get("Money", {})
    if set(money.get("required", [])) != {"amountMinor", "currency"}:
        report.error(
            path, "openapi.money", "Money must require amountMinor and currency"
        )
    if money.get("properties", {}).get("amountMinor", {}).get("type") != "integer":
        report.error(path, "openapi.money", "Money.amountMinor must be integer")


def validate_openapi_operations(
    report: Report,
    path: Path,
    document: dict[str, Any],
    global_ids: dict[str, Path],
) -> None:
    if not {"/health/live", "/health/ready"}.issubset(document.get("paths", {})):
        report.error(
            path, "openapi.health", "both /health/live and /health/ready are required"
        )
    schemes = document.get("components", {}).get("securitySchemes", {})
    operation_count = 0
    for method, route, operation in operations(document):
        operation_count += 1
        operation_id = operation.get("operationId")
        if not isinstance(operation_id, str) or not operation_id:
            report.error(
                path, "openapi.operation-id", f"{method} {route} has no operationId"
            )
        elif operation_id in global_ids:
            report.error(
                path,
                "openapi.operation-id",
                f"duplicate {operation_id}; first in {global_ids[operation_id]}",
            )
        else:
            global_ids[operation_id] = path
        refs = parameter_refs(operation)
        if not any(
            f"#/components/parameters/{name}" in refs for name in CORRELATION_PARAMETERS
        ):
            report.error(
                path,
                "openapi.trace-headers",
                f"{method} {route} missing CorrelationId or RequiredCorrelationId",
            )
        if "#/components/parameters/Traceparent" not in refs:
            report.error(
                path, "openapi.trace-headers", f"{method} {route} missing Traceparent"
            )
        seen: set[tuple[str, str]] = set()
        for key in resolved_parameter_keys(document, operation):
            if key in seen:
                report.error(
                    path,
                    "openapi.duplicate-parameter",
                    f"{method} {route} declares {key[0]} in {key[1]} more than once",
                )
            seen.add(key)
        mutation = (
            method in {"POST", "PUT", "PATCH", "DELETE"}
            and route not in MUTATION_EXCLUSIONS
        )
        if mutation and not route.startswith("/health/"):
            if "#/components/parameters/IdempotencyKey" not in refs:
                report.error(
                    path,
                    "openapi.idempotency",
                    f"{method} {route} missing Idempotency-Key",
                )
        precondition = (
            method in {"PUT", "PATCH", "DELETE"}
            or (method == "POST" and "{" in route and route not in MUTATION_EXCLUSIONS)
        ) and route not in PRECONDITION_EXCLUSIONS
        if precondition and not any(
            f"#/components/parameters/{name}" in refs for name in PRECONDITION_PARAMETERS
        ):
            report.error(path, "openapi.if-match", f"{method} {route} missing If-Match")
        responses = operation.get("responses", {})
        if not any(str(code).startswith("2") for code in responses):
            report.error(
                path, "openapi.success", f"{method} {route} has no 2xx response"
            )
        if not route.startswith("/health/") and not any(
            str(code).startswith(("4", "5")) for code in responses
        ):
            report.error(
                path,
                "openapi.error-response",
                f"{method} {route} has no error response",
            )
        effective_security = operation.get("security", document.get("security"))
        if effective_security is None:
            report.error(
                path, "openapi.security", f"{method} {route} has no security decision"
            )
        elif isinstance(effective_security, list):
            for requirement in effective_security:
                if isinstance(requirement, dict):
                    unknown = set(requirement) - set(schemes)
                    if unknown:
                        report.error(
                            path,
                            "openapi.security",
                            f"unknown schemes {sorted(unknown)}",
                        )
    report.counts[path.name] = operation_count


def validate_openapi(
    report: Report,
    artifacts: list[Artifact],
    validator_class: Any,
    format_checker: Any,
) -> None:
    global_ids: dict[str, Path] = {}
    for artifact in artifacts:
        if artifact.format != OPENAPI_FORMAT or not artifact.path.is_file():
            continue
        document = report.capture(read_yaml, artifact.path)
        if document is None:
            continue
        if document.get("openapi") != "3.1.0":
            report.error(artifact.path, "openapi.version", "must be OpenAPI 3.1.0")
        servers = document.get("servers", [])
        if len(servers) != 1 or not isinstance(servers[0], dict):
            report.error(
                artifact.path, "openapi.server", "exactly one local server is required"
            )
        else:
            parsed = urlsplit(str(servers[0].get("url", "")))
            if parsed.hostname != "localhost" or parsed.port != artifact.port:
                report.error(
                    artifact.path,
                    "openapi.port",
                    f"server must use localhost:{artifact.port}",
                )
            if parsed.username or parsed.password:
                report.error(
                    artifact.path,
                    "openapi.credentials",
                    "server URL must not contain credentials",
                )
        for ref in walk_refs(document):
            if not ref.startswith("#"):
                report.error(
                    artifact.path,
                    "openapi.external-ref",
                    f"external $ref is forbidden: {ref}",
                )
                continue
            try:
                json_pointer(document, ref)
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                report.error(artifact.path, "openapi.broken-ref", f"{ref}: {exc}")
        for cycle in ref_cycles(document):
            report.error(artifact.path, "openapi.ref-cycle", cycle)
        validate_openapi_components(report, artifact.path, document)
        validate_openapi_operations(report, artifact.path, document, global_ids)
        examples = sum(
            1
            for item in walk_mappings(document)
            if "example" in item or "examples" in item
        )
        if examples == 0:
            report.error(
                artifact.path,
                "openapi.examples",
                "at least one explicit example is required",
            )
        for name in ("ErrorResponse", "Money", "HealthStatus"):
            schema = document.get("components", {}).get("schemas", {}).get(name)
            if not isinstance(schema, dict):
                continue
            try:
                validator_class.check_schema(schema)
                if "example" in schema:
                    validator_class(schema, format_checker=format_checker).validate(
                        schema["example"]
                    )
            except (
                Exception
            ) as exc:  # jsonschema exposes multiple validation exception types
                report.error(artifact.path, "openapi.schema-example", f"{name}: {exc}")
        for mapping in walk_mappings(document):
            if mapping.get("format") == "date-time" and "pattern" not in mapping:
                report.error(
                    artifact.path, "openapi.utc", "date-time schema must constrain UTC"
                )
    report.counts["operationIds"] = len(global_ids)


def validate_asyncapi(
    report: Report, validator_class: Any, format_checker: Any
) -> None:
    path = CONTRACTS_ROOT / "realtime-service.asyncapi.yaml"
    document = report.capture(read_yaml, path)
    if document is None:
        return
    if document.get("asyncapi") != "3.0.0":
        report.error(path, "asyncapi.version", "must be AsyncAPI 3.0.0")
    server = document.get("servers", {}).get("local", {})
    if (
        server.get("protocol") not in {"ws", "wss"}
        or server.get("host") != "localhost:8008"
    ):
        report.error(
            path, "asyncapi.server", "local WebSocket server must use port 8008"
        )
    channel = document.get("channels", {}).get("bookingStatus", {})
    if channel.get("address") != "/ws/bookings/{bookingId}":
        report.error(path, "asyncapi.channel", "booking WebSocket address is incorrect")
    for ref in walk_refs(document):
        if not ref.startswith("#"):
            report.error(
                path, "asyncapi.external-ref", f"external $ref is forbidden: {ref}"
            )
        elif not ref.startswith("#/$defs/"):
            try:
                json_pointer(document, ref)
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                report.error(path, "asyncapi.broken-ref", f"{ref}: {exc}")
    operations_found = document.get("operations", {})
    if set(operations_found) != {"receiveRealtimeClientMessage", "sendRealtimeStatus"}:
        report.error(
            path, "asyncapi.operations", "receive and send operations are required"
        )
    messages = document.get("components", {}).get("messages", {})
    for name in ("ClientMessage", "StatusMessage", "ControlMessage"):
        payload = messages.get(name, {}).get("payload")
        if not isinstance(payload, dict):
            report.error(path, "asyncapi.payload", f"{name} payload is missing")
            continue
        try:
            validator_class.check_schema(payload)
            validator = validator_class(payload, format_checker=format_checker)
            for example in payload.get("examples", []):
                validator.validate(example)
        except Exception as exc:
            report.error(path, "asyncapi.schema-example", f"{name}: {exc}")
    if len(document.get("x-close-codes", [])) < 5:
        report.error(
            path, "asyncapi.close-codes", "stable close-code registry is required"
        )
    report.counts["asyncapiMessages"] = len(messages)


def validate_event_schema(
    report: Report, validator_class: Any, format_checker: Any
) -> None:
    path = CONTRACTS_ROOT / "event-messages.schema.json"
    schema = report.capture(read_json, path)
    if schema is None:
        return
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        report.error(path, "json-schema.dialect", "Draft 2020-12 is required")
    for ref in walk_refs(schema):
        if not ref.startswith("#"):
            report.error(
                path, "json-schema.external-ref", f"external $ref is forbidden: {ref}"
            )
            continue
        try:
            json_pointer(schema, ref)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            report.error(path, "json-schema.broken-ref", f"{ref}: {exc}")
    try:
        validator_class.check_schema(schema)
    except Exception as exc:
        report.error(path, "json-schema.compile", str(exc))
        return
    definitions = schema.get("$defs", {})
    event_refs = schema.get("oneOf", [])
    event_count = 0
    for item in event_refs:
        if not isinstance(item, dict) or not isinstance(item.get("$ref"), str):
            report.error(
                path, "json-schema.oneOf", "event variants must be local $ref entries"
            )
            continue
        ref = item["$ref"]
        event_schema = json_pointer(schema, ref)
        wrapper = {"$schema": schema["$schema"], "$ref": ref, "$defs": definitions}
        validator = validator_class(wrapper, format_checker=format_checker)
        examples = (
            event_schema.get("examples", []) if isinstance(event_schema, dict) else []
        )
        if not examples:
            report.error(path, "json-schema.examples", f"{ref} has no example")
        for example in examples:
            try:
                validator.validate(example)
            except Exception as exc:
                report.error(path, "json-schema.example", f"{ref}: {exc}")
        event_count += 1
    for example_path in sorted((CONTRACTS_ROOT / "examples/events").glob("*.json")):
        example = report.capture(read_json, example_path)
        if example is None:
            continue
        try:
            validator_class(schema, format_checker=format_checker).validate(example)
        except Exception as exc:
            report.error(example_path, "json-schema.external-example", str(exc))
    report.counts["eventMessages"] = event_count


def validate_http_examples(
    report: Report, validator_class: Any, format_checker: Any
) -> None:
    index_path = CONTRACTS_ROOT / "examples/http/index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        report.error(index_path, "example.index", str(exc))
        return
    if not isinstance(index, list):
        report.error(index_path, "example.index", "HTTP example index must be a list")
        return
    documents: dict[str, dict[str, Any]] = {}
    count = 0
    for entry in index:
        if not isinstance(entry, dict):
            report.error(index_path, "example.entry", "entry must be an object")
            continue
        contract_name = entry.get("openapi")
        schema_name = entry.get("schema")
        schema_ref = entry.get("schemaRef")
        filename = entry.get("file")
        valid_schema_selector = isinstance(schema_name, str) ^ isinstance(
            schema_ref, str
        )
        if (
            not isinstance(contract_name, str)
            or not isinstance(filename, str)
            or not valid_schema_selector
        ):
            report.error(index_path, "example.entry", f"invalid entry: {entry}")
            continue
        contract = documents.get(contract_name)
        if contract is None:
            contract = report.capture(read_yaml, CONTRACTS_ROOT / contract_name)
            if contract is None:
                continue
            documents[contract_name] = contract
        instance = report.capture(read_json, index_path.parent / filename)
        if instance is None:
            continue
        ref = (
            schema_ref
            if isinstance(schema_ref, str)
            else f"#/components/schemas/{schema_name}"
        )
        wrapper = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": ref,
            "components": contract.get("components", {}),
            "paths": contract.get("paths", {}),
        }
        try:
            validator_class(wrapper, format_checker=format_checker).validate(instance)
        except Exception as exc:
            report.error(
                index_path.parent / filename,
                "example.http",
                f"{contract_name}{ref}: {exc}",
            )
        count += 1
    report.counts["httpExamples"] = count


def validate_soap(report: Report, etree: Any) -> None:
    xsd_path = CONTRACTS_ROOT / "seat-inventory.xsd"
    wsdl_path = CONTRACTS_ROOT / "seat-inventory.wsdl"
    try:
        schema = etree.XMLSchema(etree.parse(str(xsd_path)))
        wsdl = etree.parse(str(wsdl_path))
    except (OSError, etree.XMLSyntaxError, etree.XMLSchemaParseError) as exc:
        report.error(xsd_path, "soap.compile", str(exc))
        return
    root = wsdl.getroot()
    namespace = "urn:event-ticketing:seat:v1"
    if root.get("targetNamespace") != namespace:
        report.error(wsdl_path, "soap.namespace", f"must be {namespace}")
    ns = {
        "wsdl": "http://schemas.xmlsoap.org/wsdl/",
        "soap": "http://schemas.xmlsoap.org/wsdl/soap/",
    }
    expected = {
        "GetSeatMap",
        "CheckAvailability",
        "ReserveSeats",
        "GetReservation",
        "ExtendReservation",
        "ConfirmSeats",
        "ReleaseSeats",
        "ExpireReservations",
        "ConfigureInventory",
    }
    found = {
        node.get("name")
        for node in root.xpath("./wsdl:portType/wsdl:operation", namespaces=ns)
    }
    if found != expected:
        report.error(
            wsdl_path,
            "soap.operations",
            f"expected {sorted(expected)}, got {sorted(found)}",
        )
    for operation in root.xpath("./wsdl:binding/wsdl:operation", namespaces=ns):
        name = operation.get("name")
        action = operation.find("soap:operation", namespaces=ns)
        if action is None or action.get("soapAction") != f"{namespace}/{name}":
            report.error(wsdl_path, "soap.action", f"invalid SOAP action for {name}")
    addresses = root.xpath(
        "./wsdl:service/wsdl:port/soap:address/@location", namespaces=ns
    )
    if addresses != ["http://localhost:8003/soap"]:
        report.error(
            wsdl_path, "soap.port", "SOAP address must use localhost:8003/soap"
        )
    text = wsdl_path.read_text(encoding="utf-8")
    if "SeatServiceFault" not in text or "Service JWT" not in text:
        report.error(
            wsdl_path,
            "soap.security-error",
            "Service JWT documentation and SeatServiceFault are required",
        )
    examples = sorted((CONTRACTS_ROOT / "examples/soap").glob("*.xml"))
    soap_namespace = "http://schemas.xmlsoap.org/soap/envelope/"
    request_names: set[str] = set()
    for example in examples:
        try:
            document = etree.parse(str(example))
            body = document.getroot().find(f"{{{soap_namespace}}}Body")
            if body is None or len(body) != 1:
                raise ValueError("SOAP Body must contain exactly one element")
            payload = body[0]
            if payload.tag == f"{{{soap_namespace}}}Fault":
                details = payload.xpath(".//*[local-name()='SeatServiceFault']")
                if len(details) != 1 or not schema.validate(details[0]):
                    raise ValueError(
                        schema.error_log.last_error or "fault detail does not validate"
                    )
            else:
                request_names.add(etree.QName(payload).localname)
                schema.assertValid(payload)
        except (
            OSError,
            ValueError,
            etree.XMLSyntaxError,
            etree.DocumentInvalid,
        ) as exc:
            report.error(example, "soap.example", str(exc))
    expected_requests = {f"{name}Request" for name in expected}
    if request_names != expected_requests:
        report.error(
            CONTRACTS_ROOT / "examples/soap",
            "soap.examples",
            "one request example per operation is required",
        )
    report.counts["soapOperations"] = len(found)
    report.counts["soapExamples"] = len(examples)


def validate_contracts() -> Report:
    report = Report()
    try:
        validator_class, format_checker_class, etree = require_validation_dependencies()
    except ContractError as exc:
        report.errors.append(exc)
        return report
    artifacts = validate_manifest(report)
    validate_catalog_shape(report)
    validate_openapi(report, artifacts, validator_class, format_checker_class())
    validate_asyncapi(report, validator_class, format_checker_class())
    validate_event_schema(report, validator_class, format_checker_class())
    validate_http_examples(report, validator_class, format_checker_class())
    validate_soap(report, etree)
    return report


def main() -> int:
    report = validate_contracts()
    for error in report.errors:
        print(f"ERROR {error}")
    counts = " ".join(f"{key}={value}" for key, value in sorted(report.counts.items()))
    print(f"CONTRACT_COUNTS {counts}")
    if report.errors:
        print(f"CONTRACT_VALIDATION FAIL errors={len(report.errors)}")
        return 1
    print("CONTRACT_VALIDATION PASS errors=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
