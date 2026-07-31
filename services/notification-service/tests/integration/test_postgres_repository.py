"""Integration test - can PostgreSQL that dang chay (xem conftest.py).
Chay bang: pytest tests/integration -m integration

Test nhung thu InMemoryDeliveryRepository KHONG the bao dam: sequence
sinh id dung tai tang DB, UNIQUE constraint that chan trung correlationId
ke ca khi bypass kiem tra o tang application, va du lieu con lai sau khi
"restart" (engine moi, ket noi moi).
"""
from __future__ import annotations

import pytest

from app.domain.entities import Delivery
from app.domain.enums import NotificationType
from app.domain.exceptions import DuplicateCorrelationError
from app.infrastructure.database.repositories import PostgresDeliveryRepository

pytestmark = pytest.mark.integration


def _delivery(delivery_id: str, correlation_id: str) -> Delivery:
    return Delivery.create(
        delivery_id,
        NotificationType.BOOKING_CONFIRMED,
        correlation_id,
        "an@example.com",
        "Dat ve thanh cong",
        "<p>noi dung</p>",
    )


def test_next_id_increments_via_db_sequence(postgres_repo: PostgresDeliveryRepository) -> None:
    assert postgres_repo.next_id() == "N000001"
    assert postgres_repo.next_id() == "N000002"
    assert postgres_repo.next_id() == "N000003"


def test_add_and_get_round_trip(postgres_repo: PostgresDeliveryRepository) -> None:
    postgres_repo.add(_delivery("N000001", "corr-1"))

    fetched = postgres_repo.get("N000001")
    assert fetched is not None
    assert fetched.correlation_id == "corr-1"
    assert fetched.to_email == "an@example.com"


def test_get_missing_returns_none(postgres_repo: PostgresDeliveryRepository) -> None:
    assert postgres_repo.get("N999999") is None


def test_unique_correlation_id_enforced_at_database_level(
    postgres_repo: PostgresDeliveryRepository,
) -> None:
    """Mo phong race condition: 2 lan add() cung correlationId, bo qua het
    kiem tra o tang application (exists_by_correlation_id). UNIQUE
    constraint tren cot correlation_id phai la hang rao cuoi cung chan
    duoc, khong duoc phep tao ra 2 ban ghi trung correlationId."""
    postgres_repo.add(_delivery("N000001", "corr-trung"))

    with pytest.raises(DuplicateCorrelationError):
        postgres_repo.add(_delivery("N000002", "corr-trung"))

    assert postgres_repo.get("N000002") is None


def test_exists_by_correlation_id(postgres_repo: PostgresDeliveryRepository) -> None:
    assert postgres_repo.exists_by_correlation_id("corr-x") is False
    postgres_repo.add(_delivery("N000001", "corr-x"))
    assert postgres_repo.exists_by_correlation_id("corr-x") is True


def test_data_survives_new_engine_connection(
    postgres_repo: PostgresDeliveryRepository,
) -> None:
    """Khac biet cot loi so voi InMemoryDeliveryRepository: du lieu phai
    con nguyen khi mo mot ket noi/engine hoan toan moi (mo phong service
    restart)."""
    from app.infrastructure.database.session import dispose_engine

    postgres_repo.add(_delivery("N000001", "corr-restart"))

    dispose_engine()  # dong het connection pool hien tai

    fresh_repo = PostgresDeliveryRepository()
    fetched = fresh_repo.get("N000001")
    assert fetched is not None
    assert fetched.correlation_id == "corr-restart"


def test_list_all_returns_every_delivery(postgres_repo: PostgresDeliveryRepository) -> None:
    postgres_repo.add(_delivery("N000001", "corr-a"))
    postgres_repo.add(_delivery("N000002", "corr-b"))

    deliveries = list(postgres_repo.list_all())
    assert {d.id for d in deliveries} == {"N000001", "N000002"}
