from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "contracts"
MATRIX_PATH = ROOT / "gateway" / "booking-orchestrator" / "ESB_DEPENDENCIES.yaml"
FIXTURES_PATH = Path(__file__).with_name("fixtures.yaml")
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
PUBLIC = {
    ("GET", "/api/events", "publicListEvents"),
    ("GET", "/api/events/{eventId}", "publicGetEvent"),
    ("POST", "/api/bookings", "placeBooking"),
    ("GET", "/api/bookings/{bookingId}", "publicGetBooking"),
    ("POST", "/api/bookings/{bookingId}/cancel", "publicCancelBooking"),
    ("GET", "/api/health", "aggregateHealth"),
    ("GET", "/api/traces/{correlationId}", "getWorkflowTrace"),
    ("POST", "/api/realtime/ws-tickets", "issueRealtimeWebSocketTicket"),
}
REQUIRED_SCENARIOS = {
    "ESB-EVENT-READ-001", "ESB-BOOKING-GET-001", "ESB-BOOKING-SUCCESS-001",
    "ESB-SEAT-UNAVAILABLE-001", "ESB-RESERVE-FAIL-AFTER-BOOKING-001",
    "ESB-RESERVE-UNKNOWN-001", "ESB-PAYMENT-FAILED-001", "ESB-PAYMENT-UNKNOWN-001",
    "ESB-TICKET-FAIL-AFTER-CAPTURE-001", "ESB-CANCEL-001", "ESB-IDEMPOTENCY-REPLAY-001",
    "ESB-AUTH-DENY-001", "ESB-NOTIFICATION-FAIL-001", "ESB-REALTIME-TICKET-001",
    "ESB-SOAP-FAULT-MAP-001", "ESB-CORRELATION-001",
}


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_document(path: Path) -> dict[str, Any]:
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return load_yaml(path)


def json_pointer(document: Any, pointer: str) -> Any:
    current = document
    if pointer in {"", "/"}:
        return current
    for raw in pointer.lstrip("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def resolve_ref(ref: str, document: dict[str, Any], source: Path) -> tuple[Any, dict[str, Any], Path]:
    if ref.startswith("#"):
        return json_pointer(document, ref[1:]), document, source
    path_part, separator, fragment = ref.partition("#")
    target_source = (source.parent / path_part).resolve()
    target_document = load_document(target_source)
    target = json_pointer(target_document, fragment) if separator else target_document
    return target, target_document, target_source


def dereference_schema(
    schema: Any,
    document: dict[str, Any],
    source: Path,
    trail: tuple[tuple[Path, str], ...] = (),
) -> Any:
    if isinstance(schema, list):
        return [dereference_schema(value, document, source, trail) for value in schema]
    if not isinstance(schema, dict):
        return schema
    if "$ref" in schema:
        ref = schema["$ref"]
        marker = (source, ref)
        if marker in trail:
            return schema
        target, target_document, target_source = resolve_ref(ref, document, source)
        resolved = dereference_schema(target, target_document, target_source, (*trail, marker))
        siblings = {key: value for key, value in schema.items() if key != "$ref"}
        if not siblings:
            return resolved
        return {"allOf": [resolved, dereference_schema(siblings, document, source, trail)]}
    return {
        key: dereference_schema(value, document, source, trail)
        for key, value in schema.items()
    }


def schema_registry() -> Registry:
    registry = Registry()
    for path in CONTRACTS.rglob("*.schema.json"):
        schema = load_document(path)
        schema_id = schema.get("$id")
        if schema_id:
            registry = registry.with_resource(schema_id, Resource.from_contents(schema))
    return registry


def assert_valid_instance(instance: Any, schema: dict[str, Any]) -> None:
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(
        schema,
        registry=schema_registry(),
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(instance), key=lambda item: list(item.path))
    assert not errors, "; ".join(error.message for error in errors)


def find_openapi_operation(
    document: dict[str, Any], method: str, path: str
) -> dict[str, Any]:
    return document["paths"][path][method.lower()]


def resolved_parameters(
    document: dict[str, Any], source: Path, path: str, operation: dict[str, Any]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for parameter in [*document["paths"][path].get("parameters", []), *operation.get("parameters", [])]:
        if "$ref" in parameter:
            parameter, _, _ = resolve_ref(parameter["$ref"], document, source)
        result.append(parameter)
    return result


def response_schema(
    document: dict[str, Any], source: Path, operation: dict[str, Any], status: str
) -> dict[str, Any]:
    response = operation["responses"][status]
    if "$ref" in response:
        response, response_document, response_source = resolve_ref(response["$ref"], document, source)
    else:
        response_document, response_source = document, source
    schema = response.get("content", {}).get("application/json", {}).get("schema")
    assert schema is not None, f"missing JSON schema for response {status}"
    return dereference_schema(schema, response_document, response_source)


def matrix_schema(ref: str, esb: dict[str, Any], esb_path: Path) -> dict[str, Any]:
    target, document, source = resolve_ref(ref, esb, esb_path)
    return dereference_schema(target, document, source)


def openapi_operations(document: dict[str, Any]) -> set[tuple[str, str, str]]:
    return {
        (method.upper(), path, operation["operationId"])
        for path, path_item in document.get("paths", {}).items()
        for method, operation in path_item.items()
        if method in HTTP_METHODS and isinstance(operation, dict)
    }


def operation_map(matrix: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {operation["publicOperationId"]: operation for operation in matrix["publicOperations"]}


def scenario_map() -> dict[str, dict[str, Any]]:
    return {item["scenarioId"]: item for item in load_yaml(FIXTURES_PATH)["scenarios"]}


def walk_provider_calls(node: Any) -> Iterable[dict[str, Any]]:
    if isinstance(node, dict):
        if node.get("protocol") in {"REST", "SOAP", "INTERNAL_REST"} and "operationId" in node:
            yield node
        for value in node.values():
            yield from walk_provider_calls(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_provider_calls(value)


def place_sequence(matrix: dict[str, Any]) -> list[str]:
    return [call["operationId"] for call in operation_map(matrix)["placeBooking"]["providerCalls"]]


def matrix_errors(matrix: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if matrix.get("crossServiceDatabaseAccess") != "forbidden":
        errors.append("cross-service database access")
    public = {(item["method"], item["path"], item["publicOperationId"]) for item in matrix.get("publicOperations", [])}
    if public != PUBLIC:
        errors.append("public operations")
    sequence = place_sequence(matrix)
    for before, after in [
        ("CheckAvailability", "createBooking"),
        ("createBooking", "ReserveSeats"),
        ("ReserveSeats", "bookingReservation"),
        ("ReserveSeats", "createPayment"),
        ("capturePayment", "issueTickets"),
        ("issueTickets", "bookingTickets"),
        ("bookingTickets", "ConfirmSeats"),
        ("ConfirmSeats", "bookingConfirm"),
    ]:
        if before not in sequence or after not in sequence or sequence.index(before) >= sequence.index(after):
            errors.append(f"ordering {before}->{after}")
    capture = next(call for call in operation_map(matrix)["placeBooking"]["providerCalls"] if call["operationId"] == "capturePayment")
    if capture.get("retryClass") != "reconciliationOnly":
        errors.append("payment capture retry")
    reserve = next(call for call in operation_map(matrix)["placeBooking"]["providerCalls"] if call["operationId"] == "ReserveSeats")
    if reserve.get("retryClass") != "idempotentCommand":
        errors.append("reserve retry class")
    unknown_calls = matrix["workflowDefinitions"]["bookingCreation"]["branchProviderCalls"]["reserveSeatsUnknown"]
    if [call.get("operationId") for call in unknown_calls] != ["ReserveSeats"]:
        errors.append("reserve unknown same-key replay")
    elif not all(
        token in unknown_calls[0].get("inputFrom", "")
        for token in ("exact original ReserveSeats request", "same stable-workflow-step-key")
    ):
        errors.append("reserve replay payload or key")
    for operation_id in ("receiveEventWebhook", "ingestRealtimeStatusEvent"):
        call = next(call for call in operation_map(matrix)["placeBooking"]["providerCalls"] if call["operationId"] == operation_id)
        if call.get("criticalPath") is not False or call.get("bookingRollbackOnFailure") is not False:
            errors.append(f"side effect isolation {operation_id}")
    for public_id in ("publicGetBooking", "publicCancelBooking", "issueRealtimeWebSocketTicket"):
        calls = operation_map(matrix)[public_id]["providerCalls"]
        if not calls or calls[0]["operationId"] != "decideBookingResourceAccess":
            errors.append(f"access order {public_id}")
    return errors


def test_matrix_metadata_matches_freeze() -> None:
    matrix = load_yaml(MATRIX_PATH)
    freeze = load_yaml(CONTRACTS / "FREEZE.lock.yaml")
    assert matrix["version"] == "1.0.0"
    assert matrix["contractFreezeId"] == freeze["freezeId"]
    assert matrix["contractFreezeSha256"] == freeze["catalogSha256"]
    assert matrix["orchestrator"] == "booking-orchestrator"
    assert matrix["documentClass"] == "derived-orchestration-design"
    assert matrix["canonicalContract"] is False
    assert matrix["canonicalAuthority"] == "contracts/**"


def test_all_eight_public_esb_operations_exist_in_contract_and_matrix() -> None:
    esb = load_yaml(CONTRACTS / "openapi" / "esb-public-api.yaml")
    assert openapi_operations(esb) == PUBLIC
    matrix_public = {(item["method"], item["path"], item["publicOperationId"]) for item in load_yaml(MATRIX_PATH)["publicOperations"]}
    assert matrix_public == PUBLIC


def test_every_public_operation_has_required_planning_fields() -> None:
    required = {
        "publicOperationId", "authentication", "authorization", "requiredHeaders",
        "acceptedHeaders", "generatedHeaders", "security",
        "requestSchema", "responseSchemas", "providerCalls", "timeoutPolicy",
        "retryPolicy", "idempotencyPolicy", "errorMappings", "workflowResult",
    }
    for operation in load_yaml(MATRIX_PATH)["publicOperations"]:
        assert required <= operation.keys(), operation["publicOperationId"]


def assert_provider_call_resolves(
    operation: dict[str, Any], manifest_map: dict[str, str], openapi_cache: dict[str, set[tuple[str, str, str]]],
    soap_operations: set[str], soap_actions: set[str],
) -> None:
    assert manifest_map[operation["contractId"]] == operation["canonicalPath"]
    if operation["method"] == "SOAP":
        assert operation["operationId"] in soap_operations
        assert operation["path"] in soap_actions
    else:
        operations = openapi_cache.setdefault(
            operation["canonicalPath"],
            openapi_operations(load_yaml(CONTRACTS / operation["canonicalPath"])),
        )
        assert (operation["method"], operation["path"], operation["operationId"]) in operations


def test_every_provider_operation_and_use_site_resolves_to_canonical_contract() -> None:
    matrix = load_yaml(MATRIX_PATH)
    manifest = load_yaml(CONTRACTS / "manifest.yaml")
    manifest_map = {entry["contractId"]: entry["canonicalPath"] for entry in manifest["contracts"]}
    wsdl_root = ElementTree.parse(CONTRACTS / "soap" / "seat-inventory.wsdl").getroot()
    ns = {"wsdl": "http://schemas.xmlsoap.org/wsdl/", "soap": "http://schemas.xmlsoap.org/wsdl/soap/"}
    soap_operations = {node.attrib["name"] for node in wsdl_root.findall("./wsdl:portType/wsdl:operation", ns)}
    soap_actions = {node.attrib["soapAction"] for node in wsdl_root.findall("./wsdl:binding/wsdl:operation/soap:operation", ns)}
    openapi_cache: dict[str, set[tuple[str, str, str]]] = {}
    registry_operations = list(matrix["providerOperations"].values())
    use_site_operations = list(walk_provider_calls(matrix["publicOperations"]))
    use_site_operations += list(walk_provider_calls(matrix["workflowDefinitions"]))
    assert registry_operations and use_site_operations
    for operation in [*registry_operations, *use_site_operations]:
        assert_provider_call_resolves(
            operation, manifest_map, openapi_cache, soap_operations, soap_actions
        )


def test_public_matrix_headers_security_requests_and_statuses_match_openapi_exactly() -> None:
    matrix = load_yaml(MATRIX_PATH)
    esb_path = CONTRACTS / "openapi" / "esb-public-api.yaml"
    esb = load_yaml(esb_path)
    for planned in matrix["publicOperations"]:
        operation = find_openapi_operation(esb, planned["method"], planned["path"])
        parameters = resolved_parameters(esb, esb_path, planned["path"], operation)
        header_parameters = [item for item in parameters if item.get("in") == "header"]
        required_headers = [item["name"] for item in header_parameters if item.get("required")]
        accepted_headers = [item["name"] for item in header_parameters if not item.get("required")]
        assert planned["requiredHeaders"] == required_headers
        assert planned["acceptedHeaders"] == accepted_headers
        assert "Authorization" not in planned["requiredHeaders"]
        effective_security = operation.get("security", esb.get("security", []))
        security_names = [name for requirement in effective_security for name in requirement]
        assert planned["security"] == security_names

        request_body = operation.get("requestBody")
        if request_body:
            canonical_request = request_body["content"]["application/json"]["schema"]
            assert planned["requestSchema"] == canonical_request.get("$ref")
        else:
            assert planned["requestSchema"] is None or planned["requestSchema"].startswith("path.")

        expected_statuses = set(operation["responses"])
        assert set(planned["responseSchemas"]) == expected_statuses
        for status, ref in planned["responseSchemas"].items():
            assert matrix_schema(ref, esb, esb_path) == response_schema(esb, esb_path, operation, status)


def test_all_eight_seat_soap_operations_and_fault_are_canonical() -> None:
    root = ElementTree.parse(CONTRACTS / "soap" / "seat-inventory.wsdl").getroot()
    ns = {"wsdl": "http://schemas.xmlsoap.org/wsdl/"}
    expected = {"GetSeatMap", "CheckAvailability", "ReserveSeats", "GetReservation", "ExtendReservation", "ConfirmSeats", "ReleaseSeats", "ExpireReservations"}
    actual = {node.attrib["name"] for node in root.findall("./wsdl:portType/wsdl:operation", ns)}
    assert actual == expected
    assert all(node.find("wsdl:fault", ns).attrib["name"] == "SeatServiceFault" for node in root.findall("./wsdl:portType/wsdl:operation", ns))


def test_seat_xsd_requires_booking_id_for_reserve_and_reservation_id_for_get() -> None:
    root = ElementTree.parse(CONTRACTS / "soap" / "seat-inventory.xsd").getroot()
    ns = {"xs": "http://www.w3.org/2001/XMLSchema"}

    def required_children(request_name: str) -> set[str]:
        sequence = root.find(
            f"./xs:element[@name='{request_name}']/xs:complexType/xs:sequence",
            ns,
        )
        assert sequence is not None
        return {
            element.attrib["name"]
            for element in sequence.findall("xs:element", ns)
            if element.attrib.get("minOccurs", "1") != "0"
        }

    assert "bookingId" in required_children("ReserveSeatsRequest")
    assert "reservationId" in required_children("GetReservationRequest")


def test_matrix_request_and_response_schema_references_resolve() -> None:
    matrix = load_yaml(MATRIX_PATH)
    esb = load_yaml(CONTRACTS / "openapi" / "esb-public-api.yaml")
    schemas = esb["components"]["schemas"]
    for operation in matrix["publicOperations"]:
        refs = [operation["requestSchema"], *operation["responseSchemas"].values()]
        for ref in refs:
            if not isinstance(ref, str):
                continue
            if ref.startswith("#/components/schemas/"):
                name = ref.removeprefix("#/components/schemas/")
                assert name in schemas
            elif ref.startswith("#/paths/"):
                assert isinstance(json_pointer(esb, ref[1:]), dict)
            elif ref.startswith("../common/"):
                assert (CONTRACTS / "openapi" / ref).resolve().is_file()
            else:
                assert ref.startswith(("path.", "inline-"))


def test_provider_calls_have_complete_contract_and_resilience_metadata() -> None:
    required = {
        "contractId", "canonicalPath", "operationId", "method", "path", "step",
        "service", "protocol", "criticality", "inputFrom", "outputTo", "timeoutClass",
        "retryClass", "idempotency", "onSuccess", "onFailure", "compensation",
    }
    calls = list(walk_provider_calls(load_yaml(MATRIX_PATH)["publicOperations"]))
    calls += list(walk_provider_calls(load_yaml(MATRIX_PATH)["workflowDefinitions"]))
    assert calls
    for call in calls:
        assert required <= call.keys(), call.get("operationId")
        assert call["protocol"] in {"REST", "SOAP", "INTERNAL_REST"}


def test_booking_happy_path_order_and_confirmation_evidence() -> None:
    matrix = load_yaml(MATRIX_PATH)
    assert matrix_errors(matrix) == []
    success = scenario_map()["ESB-BOOKING-SUCCESS-001"]
    sequence = success["providerSequence"]
    assert sequence.index("CheckAvailability") < sequence.index("createBooking")
    assert sequence.index("createBooking") < sequence.index("ReserveSeats")
    assert sequence.index("ReserveSeats") < sequence.index("bookingReservation")
    assert sequence.index("bookingReservation") < sequence.index("createPayment")
    assert sequence.index("capturePayment") < sequence.index("issueTickets")
    assert sequence.index("bookingTickets") < sequence.index("ConfirmSeats") < sequence.index("bookingConfirm")
    assert "all-confirmation-evidence" in success["requiredInvariants"]


def test_reserve_uses_booking_id_from_create_booking_output() -> None:
    matrix = load_yaml(MATRIX_PATH)
    reserve = next(
        call
        for call in operation_map(matrix)["placeBooking"]["providerCalls"]
        if call["operationId"] == "ReserveSeats"
    )
    assert "createBooking.output.bookingId" in reserve["inputFrom"]
    assert reserve["retryClass"] == "idempotentCommand"
    assert reserve["idempotency"] == "stable-workflow-step-key"


def test_determined_reserve_failure_records_booking_failure_without_compensation() -> None:
    scenario = scenario_map()["ESB-RESERVE-FAIL-AFTER-BOOKING-001"]
    assert scenario["providerSequence"][-3:] == ["createBooking", "ReserveSeats", "bookingFail"]
    assert "ReleaseSeats" not in scenario["providerSequence"]
    assert "createPayment" not in scenario["providerSequence"]
    assert "issueTickets" not in scenario["providerSequence"]
    assert scenario["expectedBookingState"] == "FAILED"
    assert scenario["expectedCompensations"] == []


def test_unknown_reserve_replays_same_command_without_get_reservation() -> None:
    scenario = scenario_map()["ESB-RESERVE-UNKNOWN-001"]
    assert scenario["providerSequence"][-4:] == [
        "createBooking",
        "ReserveSeats",
        "ReserveSeats",
        "bookingReservation",
    ]
    assert scenario["expectedPublicStatus"] == 202
    assert scenario["expectedBookingState"] == "SEAT_RESERVED"
    assert "GetReservation" not in scenario["providerSequence"]
    assert not {"createPayment", "issueTickets", "ConfirmSeats", "bookingConfirm", "ReleaseSeats"} & set(
        scenario["providerSequence"]
    )
    results = scenario["providerResults"]["ReserveSeats"]
    assert results[0]["outcome"] == "TIMEOUT_UNKNOWN"
    assert results[1]["outcome"] == "SAME_RECORDED_RESERVATION"
    replay = scenario["reserveReplay"]
    assert replay["firstAttemptRequestFingerprint"] == replay["replayRequestFingerprint"]
    assert set(replay["unchangedFields"]) == {
        "bookingId",
        "eventId",
        "seatIds",
        "ttlSeconds",
        "requestContext",
        "idempotencyKey",
    }
    assert {
        "same-idempotency-key",
        "same-request-payload",
        "idempotent-reserve-replay",
        "no-get-reservation-without-reservation-id",
    } <= set(scenario["requiredInvariants"])


def test_derived_design_contains_required_pre_payment_failure_rules() -> None:
    workflow = load_yaml(MATRIX_PATH)["workflowDefinitions"]["bookingCreation"]
    rules = workflow["failureRules"]
    assert "no compensation" in rules["createBookingFailure"]
    assert "do not call ReleaseSeats" in rules["reserveSeatsDeterminedFailure"]
    assert "identical bookingId" in rules["reserveSeatsUnknown"]
    assert "same key" in rules["reserveSeatsUnknown"]
    assert "do not call GetReservation without a known reservationId" in rules["reserveSeatsUnknown"]
    assert "keep Booking PENDING" in rules["reserveSeatsUnknown"]
    assert "schedule replay/reconciliation" in rules["reserveSeatsUnknown"]
    assert "reservationId is known" in load_yaml(MATRIX_PATH)["globalInvariants"]["getReservationPrecondition"]
    assert "ReleaseSeats then bookingFail" in rules["bookingReservationFailure"]
    assert "COMPENSATION_PENDING" in rules["bookingReservationFailure"]
    assert all(
        forbidden in rules["paymentUnknown"]
        for forbidden in ("Ticket", "ConfirmSeats", "bookingConfirm", "unsafe ReleaseSeats")
    )

    branches = workflow["branchProviderCalls"]
    assert [call["operationId"] for call in branches["reserveSeatsDeterminedFailure"]] == ["bookingFail"]
    assert [call["operationId"] for call in branches["reserveSeatsUnknown"]] == ["ReserveSeats"]
    assert branches["reserveSeatsUnknown"][0]["retryClass"] == "idempotentCommand"
    assert branches["reserveSeatsUnknown"][0]["idempotency"] == "same-stable-workflow-step-key"
    assert [call["operationId"] for call in branches["bookingReservationFailure"]] == [
        "ReleaseSeats",
        "bookingFail",
    ]


def test_payment_failed_releases_seats_and_never_issues_ticket() -> None:
    scenario = scenario_map()["ESB-PAYMENT-FAILED-001"]
    assert "ReleaseSeats" in scenario["providerSequence"]
    assert "issueTickets" not in scenario["providerSequence"]
    assert scenario["expectedBookingState"] == "FAILED"
    assert scenario["expectedCompensations"] == ["ReleaseSeats"]


def test_payment_unknown_uses_reconciliation_without_confirm_ticket_or_release() -> None:
    scenario = scenario_map()["ESB-PAYMENT-UNKNOWN-001"]
    assert scenario["expectedPublicStatus"] == 202
    assert scenario["expectedRetryClass"] == "reconciliationOnly"
    assert "reconcilePayment" in scenario["providerSequence"]
    assert not {"issueTickets", "bookingConfirm", "ReleaseSeats"} & set(scenario["providerSequence"])


def test_failure_after_capture_is_compensation_pending() -> None:
    scenario = scenario_map()["ESB-TICKET-FAIL-AFTER-CAPTURE-001"]
    assert scenario["providerResults"]["capturePayment"] == "CAPTURED"
    assert scenario["expectedBookingState"] == "COMPENSATION_PENDING"
    assert {"createRefund", "ReleaseSeats"} <= set(scenario["expectedCompensations"])


def test_access_denial_stops_before_resource_disclosure() -> None:
    scenario = scenario_map()["ESB-AUTH-DENY-001"]
    assert scenario["providerSequence"] == ["decideBookingResourceAccess"]
    assert scenario["expectedPublicStatus"] == 403
    assert "no-resource-disclosure" in scenario["requiredInvariants"]


def test_cancellation_is_access_first_and_evidence_driven() -> None:
    scenario = scenario_map()["ESB-CANCEL-001"]
    assert scenario["providerSequence"][:2] == ["decideBookingResourceAccess", "getBooking"]
    assert scenario["providerSequence"][-1] == "bookingCancel"
    assert scenario["expectedBookingState"] == "CANCELLED"
    assert "cancelled-only-after-compensation" in scenario["requiredInvariants"]


def test_side_effect_failure_does_not_rollback_confirmed_booking() -> None:
    scenario = scenario_map()["ESB-NOTIFICATION-FAIL-001"]
    assert scenario["providerResults"]["bookingConfirm"] == "CONFIRMED"
    assert scenario["providerResults"]["receiveEventWebhook"] == "FAILED"
    assert scenario["expectedBookingState"] == "CONFIRMED"
    assert scenario["expectedCompensations"] == []
    assert "no-booking-rollback" in scenario["requiredInvariants"]


def test_idempotency_replay_starts_no_provider_workflow() -> None:
    scenario = scenario_map()["ESB-IDEMPOTENCY-REPLAY-001"]
    assert scenario["providerSequence"] == []
    assert "no-new-workflow" in scenario["requiredInvariants"]


def test_correlation_is_propagated_to_every_provider_step() -> None:
    matrix = load_yaml(MATRIX_PATH)
    assert "propagated to every provider call" in matrix["globalInvariants"]["correlation"]
    scenario = scenario_map()["ESB-CORRELATION-001"]
    assert "correlation-propagated-to-every-provider-step" in scenario["requiredInvariants"]


def test_soap_fault_maps_to_common_error_without_raw_xml() -> None:
    matrix = load_yaml(MATRIX_PATH)
    mapping = matrix["errorMappingPolicy"]
    assert mapping["targetSchema"] == "contracts/common/error-response.schema.json"
    assert mapping["mappings"]["SOAP_FAULT"]["preserveOriginalFaultCode"] is True
    assert "raw_soap_xml" in mapping["redact"]
    assert scenario_map()["ESB-SOAP-FAULT-MAP-001"]["expectedPublicSchema"] == "../common/error-response.schema.json"


def test_realtime_ticket_invariants_match_canonical_contract() -> None:
    esb = load_yaml(CONTRACTS / "openapi" / "esb-public-api.yaml")
    policy = esb["components"]["schemas"]["WsTicketPolicy"]["properties"]
    assert policy["maximumTtlSeconds"]["const"] <= 60
    assert policy["singleUse"]["const"] is True
    assert policy["jtiRequired"]["const"] is True
    assert policy["issuer"]["const"] == "booking-orchestrator"
    assert policy["audience"]["const"] == "realtime-status-service"
    assert policy["scope"]["const"] == "booking:status:read"
    scenario = scenario_map()["ESB-REALTIME-TICKET-001"]
    assert scenario["providerSequence"] == ["decideBookingResourceAccess"]
    assert "no-query-token" in scenario["requiredInvariants"]


def test_cross_service_database_access_is_forbidden() -> None:
    matrix = load_yaml(MATRIX_PATH)
    assert matrix["crossServiceDatabaseAccess"] == "forbidden"
    assert matrix["globalInvariants"]["providerDatabaseRead"] == "forbidden"


def test_fixture_catalog_is_complete_and_examples_exist() -> None:
    fixtures = load_yaml(FIXTURES_PATH)["scenarios"]
    assert {item["scenarioId"] for item in fixtures} == REQUIRED_SCENARIOS
    required = {
        "scenarioId", "publicOperationId", "requestExample", "providerSequence",
        "providerResults", "expectedPublicStatus", "expectedPublicSchema",
        "expectedBookingState", "expectedCompensations", "expectedRetryClass",
        "expectedSideEffects", "requiredInvariants",
    }
    for scenario in fixtures:
        assert required <= scenario.keys()
        example = scenario["requestExample"]
        if isinstance(example, str) and example.startswith("contracts/"):
            assert (ROOT / example).is_file(), scenario["scenarioId"]
        for value in scenario["providerResults"].values():
            if isinstance(value, str) and value.startswith("contracts/"):
                assert (ROOT / value).is_file(), scenario["scenarioId"]
        if scenario["expectedCompensations"] or scenario["expectedBookingState"] == "COMPENSATION_PENDING":
            assert "scheduledCompensations" in scenario
            assert "completedCompensations" in scenario


def test_fixture_requests_and_expected_schemas_validate_with_draft_2020_12_engine() -> None:
    fixtures = load_yaml(FIXTURES_PATH)
    esb_path = CONTRACTS / "openapi" / "esb-public-api.yaml"
    esb = load_yaml(esb_path)
    for schema_name, example_name in (
        ("PlaceBookingRequest", "placeBooking"),
        ("WsTicketRequest", "realtimeTicket"),
    ):
        schema = dereference_schema(esb["components"]["schemas"][schema_name], esb, esb_path)
        instance = fixtures["requestExamples"][example_name]
        assert_valid_instance(instance, schema)

    for scenario in fixtures["scenarios"]:
        expected_ref = scenario["expectedPublicSchema"]
        schema = matrix_schema(expected_ref, esb, esb_path)
        Draft202012Validator.check_schema(schema)


def test_json_provider_fixture_files_validate_against_canonical_component_schemas() -> None:
    mappings = {
        "event-success.json": ("event-service.yaml", "Event"),
        "booking-success.json": ("booking-service.yaml", "Booking"),
        "booking-access-owner.json": ("booking-service.yaml", "BookingAccessDecision"),
        "booking-access-not-owner.json": ("booking-service.yaml", "BookingAccessDecision"),
        "ticket-success.json": ("ticket-service.yaml", "Ticket"),
    }
    for filename, (contract_name, schema_name) in mappings.items():
        source = CONTRACTS / "openapi" / contract_name
        document = load_yaml(source)
        schema = dereference_schema(document["components"]["schemas"][schema_name], document, source)
        instance = json.loads((CONTRACTS / "examples" / "http" / filename).read_text(encoding="utf-8"))
        assert_valid_instance(instance, schema)


def test_freeze_digest_is_still_bound_to_matrix() -> None:
    freeze = load_yaml(CONTRACTS / "FREEZE.lock.yaml")
    matrix = load_yaml(MATRIX_PATH)
    assert matrix["contractFreezeSha256"] == freeze["catalogSha256"]
    assert freeze["manifestSha256"] == hashlib.sha256((CONTRACTS / "manifest.yaml").read_bytes()).hexdigest()


def move_reserve_before_create(value: dict[str, Any]) -> None:
    calls = operation_map(value)["placeBooking"]["providerCalls"]
    reserve_index = next(index for index, call in enumerate(calls) if call["operationId"] == "ReserveSeats")
    reserve = calls.pop(reserve_index)
    create_index = next(index for index, call in enumerate(calls) if call["operationId"] == "createBooking")
    calls.insert(create_index, reserve)


def replace_unknown_reserve_replay_with_get_reservation(value: dict[str, Any]) -> None:
    replay = value["workflowDefinitions"]["bookingCreation"]["branchProviderCalls"]["reserveSeatsUnknown"][0]
    replay.update(
        contractId="soap.seat-inventory.wsdl",
        canonicalPath="soap/seat-inventory.wsdl",
        operationId="GetReservation",
        method="SOAP",
        path="urn:event-ticketing:seat:v1/GetReservation",
        inputFrom="createBooking.output.bookingId without reservationId",
    )


@pytest.mark.parametrize(
    "mutator,expected",
    [
        (lambda value: value.update(crossServiceDatabaseAccess="allowed"), "cross-service database access"),
        (lambda value: operation_map(value)["placeBooking"]["providerCalls"].reverse(), "ordering ReserveSeats->createPayment"),
        (move_reserve_before_create, "ordering createBooking->ReserveSeats"),
        (replace_unknown_reserve_replay_with_get_reservation, "reserve unknown same-key replay"),
        (lambda value: next(call for call in operation_map(value)["placeBooking"]["providerCalls"] if call["operationId"] == "capturePayment").update(retryClass="idempotentCommand"), "payment capture retry"),
        (lambda value: next(call for call in operation_map(value)["placeBooking"]["providerCalls"] if call["operationId"] == "receiveEventWebhook").update(bookingRollbackOnFailure=True), "side effect isolation receiveEventWebhook"),
    ],
)
def test_invariant_validator_rejects_intentional_matrix_mutation(mutator: Any, expected: str) -> None:
    mutated = copy.deepcopy(load_yaml(MATRIX_PATH))
    mutator(mutated)
    assert expected in matrix_errors(mutated)
