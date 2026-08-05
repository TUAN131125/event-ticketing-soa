"""Unit test cho use case (application layer), dung InMemoryCustomerRepository
de chay nhanh, khong can PostgreSQL. Test hanh vi nghiep vu thuan tuy -
KHONG test SQL/DB (xem tests/integration cho phan do)."""

import pytest

from app.application.commands.create_customer import create_customer
from app.application.commands.deactivate_customer import deactivate_customer
from app.application.commands.find_customer import find_customer_by_email
from app.application.commands.get_customer import get_customer
from app.application.commands.update_customer import update_customer
from app.domain.enums import CustomerStatus
from app.domain.exceptions import CustomerNotFoundError, DuplicateEmailError
from app.infrastructure.database.repositories import InMemoryCustomerRepository


@pytest.fixture
def repo() -> InMemoryCustomerRepository:
    return InMemoryCustomerRepository()


def test_seed_customer_exists(repo: InMemoryCustomerRepository) -> None:
    customer = get_customer(repo, "C001")
    assert customer.email == "an@example.com"
    assert customer.status == CustomerStatus.ACTIVE


def test_create_customer_assigns_incrementing_id(
    repo: InMemoryCustomerRepository,
) -> None:
    customer = create_customer(repo, "Le Thi C", "c@example.com", "0911111111")
    assert customer.id == "C002"
    assert repo.get("C002") is not None


def test_create_customer_rejects_duplicate_email(
    repo: InMemoryCustomerRepository,
) -> None:
    with pytest.raises(DuplicateEmailError):
        create_customer(repo, "Trung Email", "an@example.com", "0900000000")


def test_create_customer_duplicate_email_is_case_insensitive(
    repo: InMemoryCustomerRepository,
) -> None:
    with pytest.raises(DuplicateEmailError):
        create_customer(repo, "Trung Email Hoa", "AN@EXAMPLE.COM", "0900000001")


def test_get_customer_not_found_raises(repo: InMemoryCustomerRepository) -> None:
    with pytest.raises(CustomerNotFoundError):
        get_customer(repo, "C999")


def test_update_customer_changes_only_given_fields(
    repo: InMemoryCustomerRepository,
) -> None:
    updated = update_customer(repo, "C001", name="Nguyen Van An 2")
    assert updated.name == "Nguyen Van An 2"
    assert updated.email == "an@example.com"  # khong doi vi khong truyen


def test_update_customer_not_found_raises(repo: InMemoryCustomerRepository) -> None:
    with pytest.raises(CustomerNotFoundError):
        update_customer(repo, "C999", name="Ai do")


def test_deactivate_customer_sets_inactive(repo: InMemoryCustomerRepository) -> None:
    customer = deactivate_customer(repo, "C001")
    assert customer.status == CustomerStatus.INACTIVE
    assert repo.get("C001").status == CustomerStatus.INACTIVE  # type: ignore[union-attr]


def test_find_customer_by_email_returns_none_when_missing(
    repo: InMemoryCustomerRepository,
) -> None:
    assert find_customer_by_email(repo, "khong-ton-tai@example.com") is None


def test_find_customer_by_email_returns_match(repo: InMemoryCustomerRepository) -> None:
    found = find_customer_by_email(repo, "an@example.com")
    assert found is not None
    assert found.id == "C001"
