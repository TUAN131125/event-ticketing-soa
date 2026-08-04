"""Unit test cho use case (application layer), dung
InMemoryEventDeliveryRepository/InMemoryTemplateRepository +
MockEmailProvider - khong can PostgreSQL."""
import pytest

from app.application.commands.receive_event import receive_event
from app.application.commands.retry_delivery import retry_delivery
from app.application.commands.upsert_template import upsert_template
from app.application.queries.get_delivery import get_delivery
from app.application.queries.list_deliveries import list_deliveries
from app.domain.enums import DeliveryStatus
from app.domain.exceptions import (
    DeliveryNotFoundError,
    DeliveryNotRetryableError,
    DuplicateEventError,
    EventSchemaInvalidError,
    TemplateVersionConflictError,
)
from app.infrastructure.database.repositories import (
    InMemoryEventDeliveryRepository,
    InMemoryTemplateRepository,
)
from app.providers.mock_provider import MockEmailProvider


@pytest.fixture
def event_repo() -> InMemoryEventDeliveryRepository:
    return InMemoryEventDeliveryRepository()


@pytest.fixture
def template_repo() -> InMemoryTemplateRepository:
    return InMemoryTemplateRepository()


def _envelope(event_id="evt-1", event_type="booking.confirmed", **data_overrides) -> dict:
    data = {"bookingId": "BK1", "email": "an@example.com", "ticketIds": ["T1"]}
    data.update(data_overrides)
    return {
        "eventId": event_id,
        "eventType": event_type,
        "schemaVersion": 1,
        "occurredAt": "2026-07-31T00:00:00Z",
        "correlationId": "corr-1",
        "aggregateId": "BK1",
        "data": data,
    }


# --- NOT-01..04 receive_event -------------------------------------------------


def test_receive_event_delivers_and_persists(event_repo, template_repo) -> None:
    provider = MockEmailProvider()
    delivery = receive_event(event_repo, template_repo, provider, _envelope())

    assert delivery.status == DeliveryStatus.DELIVERED
    assert delivery.attempt_count == 1
    assert len(provider.sent) == 1
    assert provider.sent[0]["to"] == "an@example.com"
    assert event_repo.event_exists("evt-1")


def test_receive_event_duplicate_event_id_is_rejected(event_repo, template_repo) -> None:
    provider = MockEmailProvider()
    receive_event(event_repo, template_repo, provider, _envelope())

    with pytest.raises(DuplicateEventError):
        receive_event(event_repo, template_repo, provider, _envelope())

    assert len(provider.sent) == 1  # khong gui lan 2


def test_receive_event_missing_required_field_is_422(event_repo, template_repo) -> None:
    provider = MockEmailProvider()
    envelope = _envelope(email=None)
    del envelope["data"]["email"]

    with pytest.raises(EventSchemaInvalidError):
        receive_event(event_repo, template_repo, provider, envelope)
    assert not event_repo.event_exists("evt-1")  # khong luu su kien khong hop le


def test_receive_event_unsupported_event_type_is_422(event_repo, template_repo) -> None:
    provider = MockEmailProvider()
    envelope = _envelope(event_type="payment.refunded")

    with pytest.raises(EventSchemaInvalidError):
        receive_event(event_repo, template_repo, provider, envelope)


def test_receive_event_ticket_issued(event_repo, template_repo) -> None:
    provider = MockEmailProvider()
    envelope = _envelope(
        event_id="evt-ticket-1",
        event_type="ticket.issued",
        bookingId=None,
        ticketId="TCK-1",
        eventId="EVT-1",
        email="an@example.com",
    )
    del envelope["data"]["bookingId"]
    delivery = receive_event(event_repo, template_repo, provider, envelope)
    assert delivery.status == DeliveryStatus.DELIVERED


def test_receive_event_provider_failure_marks_retry_pending(event_repo, template_repo) -> None:
    provider = MockEmailProvider(fail_times=1)
    delivery = receive_event(event_repo, template_repo, provider, _envelope())

    assert delivery.status == DeliveryStatus.RETRY_PENDING
    assert delivery.attempt_count == 1
    assert delivery.next_attempt_at is not None
    assert delivery.last_error_code == "PROVIDER_TEMPORARY_ERROR"


def test_receive_event_exceeding_max_attempts_goes_dead_letter(event_repo, template_repo) -> None:
    provider = MockEmailProvider(fail_times=1)
    delivery = receive_event(event_repo, template_repo, provider, _envelope())
    assert delivery.status == DeliveryStatus.RETRY_PENDING

    # Gia lap 4 lan retry that bai lien tiep nua (tong 5 = MAX_DELIVERY_ATTEMPTS)
    failing_provider = MockEmailProvider(fail_times=99)
    for _ in range(3):
        delivery = retry_delivery(event_repo, template_repo, failing_provider, delivery.id)
        assert delivery.status == DeliveryStatus.RETRY_PENDING
    delivery = retry_delivery(event_repo, template_repo, failing_provider, delivery.id)
    assert delivery.status == DeliveryStatus.DEAD_LETTER
    assert delivery.attempt_count == 5


# --- NOT-05/08 retry_delivery ---------------------------------------------


def test_retry_delivery_not_found(event_repo, template_repo) -> None:
    with pytest.raises(DeliveryNotFoundError):
        retry_delivery(event_repo, template_repo, MockEmailProvider(), "DLV999999")


def test_retry_delivery_rejects_already_delivered(event_repo, template_repo) -> None:
    provider = MockEmailProvider()
    delivery = receive_event(event_repo, template_repo, provider, _envelope())
    assert delivery.status == DeliveryStatus.DELIVERED

    with pytest.raises(DeliveryNotRetryableError):
        retry_delivery(event_repo, template_repo, provider, delivery.id)


def test_retry_delivery_succeeds_after_transient_failure(event_repo, template_repo) -> None:
    failing_provider = MockEmailProvider(fail_times=1)
    delivery = receive_event(event_repo, template_repo, failing_provider, _envelope())
    assert delivery.status == DeliveryStatus.RETRY_PENDING

    working_provider = MockEmailProvider()
    retried = retry_delivery(event_repo, template_repo, working_provider, delivery.id)
    assert retried.status == DeliveryStatus.DELIVERED
    assert retried.attempt_count == 2
    assert len(working_provider.sent) == 1


# --- NOT-07 get_delivery / list_deliveries ---------------------------------


def test_get_delivery_not_found(event_repo) -> None:
    with pytest.raises(DeliveryNotFoundError):
        get_delivery(event_repo, "DLV999999")


def test_list_deliveries_returns_all(event_repo, template_repo) -> None:
    provider = MockEmailProvider()
    receive_event(event_repo, template_repo, provider, _envelope("evt-a"))
    receive_event(event_repo, template_repo, provider, _envelope("evt-b"))

    deliveries = list(list_deliveries(event_repo))
    assert {d.event_id for d in deliveries} == {"evt-a", "evt-b"}


# --- NOT-09 upsert_template -------------------------------------------------


def test_upsert_template_creates_without_if_match(template_repo) -> None:
    template = upsert_template(template_repo, "welcome", "Chao mung", "<p>Hi</p>", if_match=None)
    assert template.resource_version == 1


def test_upsert_template_updates_with_correct_if_match(template_repo) -> None:
    template = upsert_template(template_repo, "welcome", "Chao mung", "<p>Hi</p>", if_match=None)
    updated = upsert_template(
        template_repo, "welcome", "Chao mung moi", "<p>Hi 2</p>", if_match=f'"{template.resource_version}"'
    )
    assert updated.resource_version == 2
    assert updated.subject == "Chao mung moi"


def test_upsert_template_rejects_wrong_if_match(template_repo) -> None:
    upsert_template(template_repo, "welcome", "Chao mung", "<p>Hi</p>", if_match=None)
    with pytest.raises(TemplateVersionConflictError):
        upsert_template(template_repo, "welcome", "Chao mung moi", "<p>Hi 2</p>", if_match='"999"')
