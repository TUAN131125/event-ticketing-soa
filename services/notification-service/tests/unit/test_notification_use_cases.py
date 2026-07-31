"""Unit test cho use case (application layer), dung InMemoryDeliveryRepository
+ MockEmailProvider de chay nhanh, khong can PostgreSQL. Test hanh vi
nghiep vu thuan tuy - KHONG test SQL/DB (xem tests/integration cho phan do).
"""
import pytest

from app.application.commands.handle_booking_confirmed import handle_booking_confirmed
from app.application.commands.handle_booking_failed import handle_booking_failed
from app.application.queries.list_deliveries import list_deliveries
from app.infrastructure.database.repositories import InMemoryDeliveryRepository
from app.providers.mock_provider import MockEmailProvider


@pytest.fixture
def repo() -> InMemoryDeliveryRepository:
    return InMemoryDeliveryRepository()


@pytest.fixture
def provider() -> MockEmailProvider:
    return MockEmailProvider()


def _confirmed_payload(correlation_id: str = "corr-1") -> dict:
    return {
        "event": "booking.confirmed",
        "correlationId": correlation_id,
        "bookingId": "BK001",
        "customerEmail": "an@example.com",
        "ticketIds": ["T001", "T002"],
    }


def _failed_payload(correlation_id: str = "corr-2") -> dict:
    return {
        "event": "booking.failed",
        "correlationId": correlation_id,
        "bookingId": "BK002",
        "customerEmail": "an@example.com",
        "reason": "Het cho",
    }


def test_booking_confirmed_sends_email_and_records_delivery(repo, provider) -> None:
    status = handle_booking_confirmed(repo, provider, _confirmed_payload())

    assert status == "SENT"
    assert len(provider.sent) == 1
    assert provider.sent[0]["to"] == "an@example.com"
    deliveries = list(list_deliveries(repo))
    assert len(deliveries) == 1
    assert deliveries[0].correlation_id == "corr-1"


def test_booking_confirmed_duplicate_correlation_id_is_ignored(repo, provider) -> None:
    handle_booking_confirmed(repo, provider, _confirmed_payload("corr-dup"))
    status = handle_booking_confirmed(repo, provider, _confirmed_payload("corr-dup"))

    assert status == "DUPLICATE_IGNORED"
    assert len(provider.sent) == 1  # khong gui lan 2
    assert len(list(list_deliveries(repo))) == 1


def test_booking_failed_sends_email_and_records_delivery(repo, provider) -> None:
    status = handle_booking_failed(repo, provider, _failed_payload())

    assert status == "SENT"
    assert len(provider.sent) == 1
    deliveries = list(list_deliveries(repo))
    assert deliveries[0].type.value == "booking.failed"


def test_booking_failed_duplicate_correlation_id_is_ignored(repo, provider) -> None:
    handle_booking_failed(repo, provider, _failed_payload("corr-dup-2"))
    status = handle_booking_failed(repo, provider, _failed_payload("corr-dup-2"))

    assert status == "DUPLICATE_IGNORED"
    assert len(provider.sent) == 1


def test_booking_failed_uses_unknown_when_email_missing(repo, provider) -> None:
    payload = _failed_payload("corr-3")
    payload["customerEmail"] = ""
    handle_booking_failed(repo, provider, payload)

    assert provider.sent[0]["to"] == "unknown"


def test_list_deliveries_returns_all_records(repo, provider) -> None:
    handle_booking_confirmed(repo, provider, _confirmed_payload("corr-a"))
    handle_booking_failed(repo, provider, _failed_payload("corr-b"))

    deliveries = list(list_deliveries(repo))
    assert {d.correlation_id for d in deliveries} == {"corr-a", "corr-b"}
