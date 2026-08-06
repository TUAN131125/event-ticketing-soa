from lxml import etree

from app.adapters.soap.seat import SEAT_NAMESPACE, SeatSoapAdapter
from app.config import Settings
from app.domain.models import Principal, RequestContext
from app.registry.service_registry import ServiceRegistry
from app.resilience.policies import ResiliencePolicy


def context() -> RequestContext:
    return RequestContext(
        correlation_id="corr-1",
        trace_id="1" * 32,
        deadline_monotonic=9_999_999_999.0,
        principal=Principal("user-1"),
    )


def test_registry_maps_logical_names_without_exposing_them_to_clients():
    registry = ServiceRegistry(Settings())
    assert registry.resolve("seat").protocol == "SOAP"
    assert registry.resolve("booking").base_url.endswith(":8004")


def test_soap_mediation_builds_canonical_get_seat_map_request():
    adapter = SeatSoapAdapter("http://seat:8003", ResiliencePolicy())
    root = etree.fromstring(
        adapter._envelope("GetSeatMap", context(), values={"eventId": "EVT-1"})
    )
    xml = etree.tostring(root).decode()
    assert SEAT_NAMESPACE == "urn:event-ticketing:seat:v1"
    assert "GetSeatMapRequest" in xml and "EVT-1" in xml
    assert "correlationId" in xml and "traceparent" in xml
    assert "callerService" in xml and "schemaVersion" in xml


def test_soap_reserve_matches_canonical_element_order_and_shape():
    adapter = SeatSoapAdapter("http://seat:8003", ResiliencePolicy())
    payload = adapter._envelope(
        "ReserveSeats",
        context(),
        idempotency_key="idem-1",
        values={"bookingId": "B-1", "eventId": "E-1"},
        seat_references=[{"seatId": "A1", "ticketTypeCode": "STD"}],
        trailing_values={"ttlSeconds": 600},
    )
    root = etree.fromstring(payload)
    request = root.xpath("//*[local-name()='ReserveSeatsRequest']")[0]
    child_names = [etree.QName(child).localname for child in request]
    assert child_names == [
        "context",
        "bookingId",
        "eventId",
        "seatIds",
        "ttlSeconds",
    ]
    assert root.xpath("string(//*[local-name()='seat']/*[local-name()='seatId'])") == "A1"
    assert (
        root.xpath("string(//*[local-name()='seat']/*[local-name()='ticketTypeCode'])")
        == "STD"
    )


def test_soap_release_uses_reason_code_not_resource_version():
    adapter = SeatSoapAdapter("http://seat:8003", ResiliencePolicy())
    payload = adapter._envelope(
        "ReleaseSeats",
        context(),
        idempotency_key="idem-release",
        values={"reservationId": "R-1", "reasonCode": "PAYMENT_FAILED"},
    )
    xml = payload.decode()
    assert "reasonCode" in xml and "PAYMENT_FAILED" in xml
    assert "expectedVersion" not in xml
