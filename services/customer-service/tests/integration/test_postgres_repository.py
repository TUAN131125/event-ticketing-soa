"""Integration test - can PostgreSQL that dang chay (xem conftest.py).
Chay bang: pytest tests/integration -m integration

Test nhung thu InMemoryCustomerRepository KHONG the bao dam: sequence
sinh id dung tai tang DB, UNIQUE constraint that chan trung email ke ca
khi bypass kiem tra o tang application, va du lieu con lai sau khi
"restart" (engine moi, ket noi moi).
"""

from __future__ import annotations

import pytest

from app.domain.entities import Customer
from app.domain.exceptions import DuplicateEmailError
from app.infrastructure.database.repositories import PostgresCustomerRepository

pytestmark = pytest.mark.integration


def test_next_id_increments_via_db_sequence(
    postgres_repo: PostgresCustomerRepository,
) -> None:
    assert postgres_repo.next_id() == "C001"
    assert postgres_repo.next_id() == "C002"
    assert postgres_repo.next_id() == "C003"


def test_add_and_get_round_trip(postgres_repo: PostgresCustomerRepository) -> None:
    customer = Customer.create("C001", "Pham Van D", "d@example.com", "0922222222")
    postgres_repo.add(customer)

    fetched = postgres_repo.get("C001")
    assert fetched is not None
    assert fetched.name == "Pham Van D"
    assert fetched.email == "d@example.com"


def test_get_missing_returns_none(postgres_repo: PostgresCustomerRepository) -> None:
    assert postgres_repo.get("C999") is None


def test_unique_email_enforced_at_database_level(
    postgres_repo: PostgresCustomerRepository,
) -> None:
    """Mo phong race condition: 2 lan add() cung email, bo qua het kiem
    tra o tang application (ensure_email_unique). UNIQUE constraint tren
    cot email phai la hang rao cuoi cung chan duoc, khong duoc phep tao
    ra 2 ban ghi trung email."""
    postgres_repo.add(
        Customer.create("C001", "Nguoi A", "trung@example.com", "0900000001")
    )

    with pytest.raises(DuplicateEmailError):
        postgres_repo.add(
            Customer.create("C002", "Nguoi B", "trung@example.com", "0900000002")
        )

    # Dam bao ban ghi thu 2 khong duoc tao du transaction that bai.
    assert postgres_repo.get("C002") is None


def test_get_by_email_is_case_insensitive(
    postgres_repo: PostgresCustomerRepository,
) -> None:
    postgres_repo.add(
        Customer.create("C001", "Vo E", "MixedCase@Example.com", "0933333333")
    )
    found = postgres_repo.get_by_email("mixedcase@example.com")
    assert found is not None
    assert found.id == "C001"


def test_update_persists_changes(postgres_repo: PostgresCustomerRepository) -> None:
    customer = Customer.create("C001", "Ban Dau", "e@example.com", "0944444444")
    postgres_repo.add(customer)

    customer.update_contact(name="Ten Moi")
    postgres_repo.update(customer)

    fetched = postgres_repo.get("C001")
    assert fetched is not None
    assert fetched.name == "Ten Moi"


def test_data_survives_new_engine_connection(
    postgres_repo: PostgresCustomerRepository,
) -> None:
    """Khac biet cot loi so voi InMemoryCustomerRepository: du lieu phai
    con nguyen khi mo mot ket noi/engine hoan toan moi (mo phong service
    restart)."""
    from app.infrastructure.database.session import dispose_engine

    postgres_repo.add(
        Customer.create("C001", "Ton Tai Sau Restart", "f@example.com", "0955555555")
    )

    dispose_engine()  # dong het connection pool hien tai

    fresh_repo = PostgresCustomerRepository()
    fetched = fresh_repo.get("C001")
    assert fetched is not None
    assert fetched.name == "Ton Tai Sau Restart"


def test_list_all_returns_every_customer(
    postgres_repo: PostgresCustomerRepository,
) -> None:
    postgres_repo.add(Customer.create("C001", "A", "a1@example.com", "0900000001"))
    postgres_repo.add(Customer.create("C002", "B", "b1@example.com", "0900000002"))

    customers = list(postgres_repo.list_all())
    assert {c.id for c in customers} == {"C001", "C002"}
