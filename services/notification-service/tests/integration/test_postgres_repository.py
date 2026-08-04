"""Integration test - can PostgreSQL that dang chay (xem conftest.py).
Chay bang: pytest tests/integration -m integration
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.domain.entities import Delivery, DeliveryAttempt, InboundEvent
from app.domain.enums import Channel, DeliveryStatus, EventType
from app.domain.exceptions import DuplicateEventError
from app.infrastructure.database.repositories import PostgresEventDeliveryRepository
from app.infrastructure.database.session import get_engine

pytestmark = pytest.mark.integration


def _event(event_id: str) -> InboundEvent:
    return InboundEvent.create(
        event_id, EventType.BOOKING_CONFIRMED, 1, "corr-1", "BK1", {"email": "an@example.com"}
    )


def _delivery(delivery_id: str, event_id: str) -> Delivery:
    return Delivery.create(delivery_id, event_id, Channel.EMAIL, "a" * 64)


def test_next_delivery_id_increments_via_db_sequence(postgres_repo: PostgresEventDeliveryRepository) -> None:
    assert postgres_repo.next_delivery_id() == "DLV000001"
    assert postgres_repo.next_delivery_id() == "DLV000002"


def test_add_event_and_delivery_round_trip(postgres_repo: PostgresEventDeliveryRepository) -> None:
    postgres_repo.add_event(_event("evt-1"))
    postgres_repo.add_delivery(_delivery("DLV000001", "evt-1"))

    delivery = postgres_repo.get_delivery("DLV000001")
    assert delivery is not None
    assert delivery.event_id == "evt-1"
    assert delivery.status == DeliveryStatus.PENDING

    event = postgres_repo.get_event("evt-1")
    assert event is not None
    assert event.payload == {"email": "an@example.com"}


def test_duplicate_event_id_rejected_at_database_level(postgres_repo: PostgresEventDeliveryRepository) -> None:
    postgres_repo.add_event(_event("evt-dup"))
    with pytest.raises(DuplicateEventError):
        postgres_repo.add_event(_event("evt-dup"))


def test_delivery_not_found_returns_none(postgres_repo: PostgresEventDeliveryRepository) -> None:
    assert postgres_repo.get_delivery("DLV999999") is None


def test_update_delivery_persists_status_transition(postgres_repo: PostgresEventDeliveryRepository) -> None:
    postgres_repo.add_event(_event("evt-2"))
    delivery = _delivery("DLV000001", "evt-2")
    postgres_repo.add_delivery(delivery)

    delivery.mark_delivered()
    postgres_repo.update_delivery(delivery)

    fetched = postgres_repo.get_delivery("DLV000001")
    assert fetched.status == DeliveryStatus.DELIVERED
    assert fetched.attempt_count == 1


def test_add_attempt_is_logged(postgres_repo: PostgresEventDeliveryRepository) -> None:
    postgres_repo.add_event(_event("evt-3"))
    postgres_repo.add_delivery(_delivery("DLV000001", "evt-3"))
    postgres_repo.add_attempt(DeliveryAttempt("DLV000001", 1, DeliveryStatus.DELIVERED, None))

    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT status FROM notification.delivery_attempts WHERE delivery_id = 'DLV000001'")
        ).fetchone()
    assert row is not None
    assert row[0] == "DELIVERED"


def test_list_deliveries_returns_every_row(postgres_repo: PostgresEventDeliveryRepository) -> None:
    postgres_repo.add_event(_event("evt-a"))
    postgres_repo.add_event(_event("evt-b"))
    postgres_repo.add_delivery(_delivery("DLV000001", "evt-a"))
    postgres_repo.add_delivery(_delivery("DLV000002", "evt-b"))

    deliveries = list(postgres_repo.list_deliveries())
    assert {d.id for d in deliveries} == {"DLV000001", "DLV000002"}


def test_data_survives_new_engine_connection(postgres_repo: PostgresEventDeliveryRepository) -> None:
    """Khac biet cot loi so voi InMemory: du lieu con nguyen qua 1
    engine/connection hoan toan moi (mo phong restart)."""
    from app.infrastructure.database.session import dispose_engine

    postgres_repo.add_event(_event("evt-restart"))
    postgres_repo.add_delivery(_delivery("DLV000001", "evt-restart"))

    dispose_engine()

    fresh_repo = PostgresEventDeliveryRepository()
    fetched = fresh_repo.get_delivery("DLV000001")
    assert fetched is not None
    assert fetched.event_id == "evt-restart"


def test_regression_pk_collision_is_not_misclassified_as_duplicate_event(
    postgres_repo: PostgresEventDeliveryRepository,
) -> None:
    """Test hoi quy cho bug thuc te da xay ra: neu insert deliveries that
    bai vi TRUNG KHOA CHINH delivery_id (khong phai trung eventId), loi
    phai duoc nem lai NGUYEN VEN (khong bi nuot thanh DuplicateEventError/
    "DUPLICATE_IGNORED" gia). add_delivery() KHONG dich IntegrityError
    thanh loi domain nao ca - day chinh la thay doi sua bug."""
    from sqlalchemy.exc import IntegrityError

    postgres_repo.add_event(_event("evt-x"))
    postgres_repo.add_event(_event("evt-y"))
    postgres_repo.add_delivery(_delivery("DLV000001", "evt-x"))

    with pytest.raises(IntegrityError):
        # Cung delivery_id "DLV000001" nhung khac event_id - phai la loi
        # trung KHOA CHINH delivery_id, khong lien quan gi eventId.
        postgres_repo.add_delivery(_delivery("DLV000001", "evt-y"))


def test_template_seeded_by_migration(postgres_repo) -> None:
    from app.infrastructure.database.repositories import PostgresTemplateRepository

    repo = PostgresTemplateRepository()
    template = repo.get("booking_confirmed")
    assert template is not None
    assert template.resource_version == 1
    assert "Dat ve thanh cong" in template.subject


def test_template_save_updates_existing_row(postgres_template_repo) -> None:
    existing = postgres_template_repo.get("booking_confirmed")
    existing.replace("Tieu de moi", "<p>Noi dung moi</p>")
    postgres_template_repo.save(existing)

    reloaded = postgres_template_repo.get("booking_confirmed")
    assert reloaded.subject == "Tieu de moi"
    assert reloaded.resource_version == 2
