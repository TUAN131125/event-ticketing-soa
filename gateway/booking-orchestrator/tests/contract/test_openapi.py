from pathlib import Path

import yaml

from app.main import create_app


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
        "checkInTicket",
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


def test_fastapi_generated_openapi_exactly_matches_the_exported_canonical_contract():
    canonical_path = Path(__file__).resolve().parents[4] / "contracts" / "esb-public-api.yaml"
    canonical = yaml.safe_load(canonical_path.read_text(encoding="utf-8"))
    assert create_app().openapi() == canonical


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
