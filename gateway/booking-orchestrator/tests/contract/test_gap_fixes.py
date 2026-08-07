from __future__ import annotations

from pathlib import Path

import yaml
from lxml import etree

from app.main import create_app
from scripts.openapi_parity import compare


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SERVICE_ROOT = Path(__file__).resolve().parents[2]
XSD_NS = {"xs": "http://www.w3.org/2001/XMLSchema"}
WSDL_NS = {"wsdl": "http://schemas.xmlsoap.org/wsdl/", "xsd": "http://www.w3.org/2001/XMLSchema"}


def test_fastapi_runtime_is_the_openapi_source_not_a_yaml_override():
    app = create_app()
    generated = app.state.generated_openapi()
    served = app.openapi()
    canonical = yaml.safe_load(
        (REPOSITORY_ROOT / "contracts/esb-public-api.yaml").read_text(encoding="utf-8")
    )
    # What is served is built from the FastAPI decorators, never loaded from a YAML file.
    assert served == generated
    assert served is not canonical
    assert "servers" not in served and "servers" in canonical
    # The canonical document is curated, so it agrees semantically rather than literally.
    assert compare(generated, canonical) == []
    assert app.openapi.__self__ is app
    assert app.state.generated_openapi.__self__ is app
    assert app.openapi.__func__ is app.state.generated_openapi.__func__


def test_every_documented_422_uses_the_canonical_error_envelope():
    document = create_app().state.generated_openapi()
    for path, path_item in document["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            response = operation.get("responses", {}).get("422")
            if response is None:
                continue
            schema = (
                response.get("content", {})
                .get("application/json", {})
                .get("schema", {})
            )
            assert schema.get("$ref") == "#/components/schemas/ErrorResponse", (
                method.upper(),
                path,
                schema,
            )


def test_booking_runtime_contract_declares_models_and_protocol_headers():
    operation = create_app().state.generated_openapi()["paths"]["/api/bookings"]["post"]
    for status in ("201", "202"):
        schema = operation["responses"][status]["content"]["application/json"]["schema"]
        assert schema["$ref"] == "#/components/schemas/BookingResult"
        assert "ETag" in operation["responses"][status]["headers"]
    assert {"Location", "Retry-After"} <= set(operation["responses"]["202"]["headers"])


def test_seat_xsd_separates_booking_selection_from_full_map():
    xsd_path = REPOSITORY_ROOT / "contracts/seat-inventory.xsd"
    tree = etree.parse(str(xsd_path))
    etree.XMLSchema(tree)

    selection = tree.xpath(
        '//xs:complexType[@name="SeatSelectionList"]//xs:element[@name="seat"]',
        namespaces=XSD_NS,
    )[0]
    seat_map = tree.xpath(
        '//xs:complexType[@name="SeatMapList"]//xs:element[@name="seat"]',
        namespaces=XSD_NS,
    )[0]
    map_reference = tree.xpath(
        '//xs:element[@name="GetSeatMapResponse"]//xs:element[@name="seats"]',
        namespaces=XSD_NS,
    )[0]
    assert selection.get("maxOccurs") == "10"
    assert seat_map.get("maxOccurs") == "20000"
    assert seat_map.get("type") == "tns:SeatMapSeat"
    assert map_reference.get("type") == "tns:SeatMapList"
    status = tree.xpath(
        '//xs:complexType[@name="SeatMapSeat"]//xs:element[@name="status"]',
        namespaces=XSD_NS,
    )[0]
    assert status.get("type") == "tns:SeatStatus"


def test_seat_wsdl_imports_xsd_and_publishes_all_canonical_operations():
    wsdl_path = REPOSITORY_ROOT / "contracts/seat-inventory.wsdl"
    tree = etree.parse(str(wsdl_path))
    imports = tree.xpath("//xsd:import", namespaces=WSDL_NS)
    assert any(item.get("schemaLocation") == "seat-inventory.xsd" for item in imports)
    operations = {
        item.get("name")
        for item in tree.xpath("//wsdl:portType/wsdl:operation", namespaces=WSDL_NS)
    }
    assert {
        "GetSeatMap",
        "CheckAvailability",
        "ReserveSeats",
        "GetReservation",
        "ExtendReservation",
        "ConfirmSeats",
        "ReleaseSeats",
        "ExpireReservations",
        "ConfigureInventory",
    } <= operations


def test_provider_contract_bundle_contains_notification_realtime_and_identity_sources():
    provider_root = REPOSITORY_ROOT / "contracts/providers"
    required = {
        "identity-service.yaml",
        "notification-service.yaml",
        "realtime-status-service.yaml",
        "realtime-status.asyncapi.yaml",
    }
    assert required <= {path.name for path in provider_root.iterdir()}
    # The Seat contract is no longer staged here: contracts/seat-inventory.{wsdl,xsd} is
    # the single canonical source and both service images copy it directly.
    assert not list(provider_root.glob("seat-inventory.*"))
    for name in required:
        document = yaml.safe_load((provider_root / name).read_text(encoding="utf-8"))
        assert isinstance(document, dict)
        assert document.get("info", {}).get("title")


def test_postgres_migration_manages_the_same_tables_as_runtime_repository():
    # The raw SQL file was promoted into the Alembic chain, which is the only migration
    # mechanism the orchestrator-migrate job runs.
    migration = (
        SERVICE_ROOT / "alembic/versions/0003_esb_refactor.py"
    ).read_text(encoding="utf-8")
    repository = (SERVICE_ROOT / "app/persistence/repositories.py").read_text(
        encoding="utf-8"
    )
    for table in ("esb_workflows_v2", "esb_outbox_v2", "esb_ws_ticket_v2"):
        assert f'"{table}"' in migration
        assert table in repository
    assert "create_all(" not in repository
