import copy
from pathlib import Path

import yaml

from app.main import create_app
from scripts.openapi_parity import compare

CANONICAL_PATH = Path(__file__).resolve().parents[4] / "contracts" / "esb-public-api.yaml"


def canonical_document():
    return yaml.safe_load(CANONICAL_PATH.read_text(encoding="utf-8"))


def operation_ids(document):
    return [
        operation.get("operationId")
        for path_item in document["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and operation.get("operationId")
    ]


def test_old_operations_preserved_and_new_facades_added():
    app = create_app()
    runtime = app.state.generated_openapi()
    operations = set(operation_ids(runtime))
    old = {
        "publicListEvents",
        "publicGetEvent",
        "placeBooking",
        "publicGetBooking",
        "publicCancelBooking",
        "aggregateHealth",
        "getWorkflowTrace",
        "issueRealtimeWebSocketTicket",
        "esbLiveness",
        "esbReadiness",
    }
    added = {
        "publicGetEventSeatMap",
        "publicListBookings",
        "publicListBookingTickets",
        "publicListTickets",
        "publicGetTicket",
        "adminCreateEvent",
        "adminReplaceEvent",
        "adminPublishEvent",
        "adminPauseEvent",
        "adminCloseEvent",
        "adminCancelEvent",
        "validateTicketForCheckIn",
        # Ticket Service owns `checkInTicket`; the gateway façade is namespaced.
        "checkInTicketViaEsb",
        "getMyCustomerProfile",
        "upsertMyCustomerProfile",
        "updateMyCustomerConsent",
        "adminGetSeatInventory",
        "adminConfigureSeatInventory",
    }
    assert old <= operations
    assert added <= operations


def test_canonical_and_runtime_operation_sets_match():
    canonical_path = Path(__file__).resolve().parents[4] / "contracts" / "esb-public-api.yaml"
    canonical = yaml.safe_load(canonical_path.read_text(encoding="utf-8"))
    app = create_app()
    runtime = app.state.generated_openapi()
    canonical_ids = operation_ids(canonical)
    runtime_ids = operation_ids(runtime)
    assert len(canonical_ids) == len(set(canonical_ids))
    assert set(canonical_ids) == set(runtime_ids)


def test_customer_id_is_compatibility_only_not_authority():
    canonical_path = Path(__file__).resolve().parents[4] / "contracts" / "esb-public-api.yaml"
    canonical = yaml.safe_load(canonical_path.read_text(encoding="utf-8"))
    request = canonical["components"]["schemas"]["PlaceBookingRequest"]
    assert "customerId" not in request["required"]
    assert request["properties"]["customerId"]["deprecated"] is True


def operation_inventory(document):
    return {
        (path, method, operation.get("operationId"))
        for path, path_item in document["paths"].items()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
        and isinstance(operation, dict)
    }


def test_canonical_and_generated_runtime_path_method_operation_inventory_match():
    canonical_path = Path(__file__).resolve().parents[4] / "contracts" / "esb-public-api.yaml"
    canonical = yaml.safe_load(canonical_path.read_text(encoding="utf-8"))
    app = create_app()
    generated = app.state.generated_openapi()
    assert operation_inventory(canonical) == operation_inventory(generated)


def test_runtime_and_canonical_contract_are_semantically_identical():
    """The canonical document is curated, so parity is semantic rather than literal.

    `compare` resolves local $refs on both sides and then requires the method/path set,
    operationIds, request bodies, response statuses, response body schemas, response
    headers, every header parameter (including whether it is required), the effective
    security of each operation and the definition of every referenced security scheme to
    match exactly. Only `title`/`description`/`example`/`summary` and the UTC pattern the
    canonical adds beside `format: date-time` are normalised away.
    """
    drift = compare(create_app().state.generated_openapi(), canonical_document())
    assert drift == [], "ESB runtime and canonical contract have drifted:\n" + "\n".join(drift)


def test_semantic_parity_detects_drift_on_either_side():
    """A parity check that cannot fail is worthless, so prove it fails."""
    runtime = create_app().state.generated_openapi()
    canonical = canonical_document()
    assert compare(runtime, canonical) == []

    # A required header disappearing from the implementation.
    mutated = copy.deepcopy(runtime)
    parameters = mutated["paths"]["/api/bookings"]["post"]["parameters"]
    mutated["paths"]["/api/bookings"]["post"]["parameters"] = [
        parameter for parameter in parameters if parameter.get("name") != "Idempotency-Key"
    ]
    assert compare(mutated, canonical)

    # A precondition silently becoming optional.
    mutated = copy.deepcopy(runtime)
    for parameter in mutated["paths"]["/api/bookings/{bookingId}/cancel"]["post"]["parameters"]:
        if parameter.get("name") == "If-Match":
            parameter["required"] = False
    assert compare(mutated, canonical)

    # An operation losing its security requirement.
    mutated = copy.deepcopy(runtime)
    mutated["paths"]["/api/tickets"]["get"]["security"] = []
    assert compare(mutated, canonical)

    # An ETag no longer advertised on a versioned resource.
    mutated = copy.deepcopy(runtime)
    mutated["paths"]["/api/events/{eventId}"]["get"]["responses"]["200"].pop("headers")
    assert compare(mutated, canonical)

    # The canonical document drifting away from the implementation.
    mutated = copy.deepcopy(canonical)
    mutated["paths"]["/api/tickets"]["get"]["operationId"] = "renamedByAccident"
    assert compare(runtime, mutated)

    mutated = copy.deepcopy(canonical)
    mutated["components"]["schemas"]["BookingResult"]["required"].remove("eventId")
    assert compare(runtime, mutated)


def test_canonical_publishes_the_reusable_contract_vocabulary():
    canonical = canonical_document()
    components = canonical["components"]

    assert canonical["servers"] == [
        {
            "url": "http://localhost:8000",
            "description": "Local contract endpoint; deployment host is supplied by configuration.",
        }
    ]
    for name, wire_name in (
        ("CorrelationId", "X-Correlation-ID"),
        ("Traceparent", "traceparent"),
        ("IdempotencyKey", "Idempotency-Key"),
        ("IfMatch", "If-Match"),
        ("OptionalIfMatch", "If-Match"),
    ):
        assert components["parameters"][name]["name"] == wire_name
    assert components["parameters"]["IfMatch"]["required"] is True
    assert components["parameters"]["OptionalIfMatch"]["required"] is False
    assert components["headers"]["ETag"]["schema"]["pattern"] == '^"[1-9][0-9]*"$'
    assert {"UserJwt", "ServiceJwt", "WebhookHmac"} <= set(components["securitySchemes"])
    # The gateway never accepts a service JWT or an inbound webhook signature; the schemes
    # are published for catalogue consistency and must stay unreferenced by any operation.
    used = {
        scheme
        for path_item in canonical["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict)
        for requirement in operation.get("security", [])
        for scheme in requirement
    }
    assert used.isdisjoint({"ServiceJwt", "WebhookHmac"})


def test_runtime_request_models_and_success_statuses_match_canonical_names():
    runtime = create_app().state.generated_openapi()
    assert runtime["paths"]["/api/bookings"]["post"]["responses"].keys() >= {"201", "202"}
    assert runtime["paths"]["/api/admin/events"]["post"]["responses"].keys() >= {"201"}
    assert (
        runtime["paths"]["/api/admin/events"]["post"]["requestBody"]["content"]
        ["application/json"]["schema"]["$ref"]
        == "#/components/schemas/EventAdminRequest"
    )
    assert (
        runtime["paths"]["/api/realtime/ws-tickets"]["post"]["requestBody"]["content"]
        ["application/json"]["schema"]["$ref"]
        == "#/components/schemas/WsTicketRequest"
    )
    cancel_body = runtime["paths"]["/api/bookings/{bookingId}/cancel"]["post"]["requestBody"]
    assert cancel_body.get("required") is not True
    assert cancel_body["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CancelBookingRequest"
    }


def test_dynamic_endpoints_do_not_advertise_resource_etags():
    canonical_path = Path(__file__).resolve().parents[4] / "contracts" / "esb-public-api.yaml"
    canonical = yaml.safe_load(canonical_path.read_text(encoding="utf-8"))
    for path, method, status in [
        ("/api/health", "get", "200"),
        ("/api/traces/{correlationId}", "get", "200"),
        ("/api/realtime/ws-tickets", "post", "201"),
        ("/health/live", "get", "200"),
        ("/health/ready", "get", "200"),
    ]:
        assert "ETag" not in canonical["paths"][path][method]["responses"][status].get(
            "headers", {}
        )
