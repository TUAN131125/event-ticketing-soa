"""Unit test cho use case (application layer), dung InMemoryCustomerRepository
de chay nhanh, khong can PostgreSQL. Test hanh vi nghiep vu thuan tuy -
KHONG test SQL/DB (xem tests/integration cho phan do)."""
import pytest

from app.application.commands.create_customer import create_customer
from app.application.commands.deactivate_customer import deactivate_customer
from app.application.commands.get_customer import get_customer
from app.application.commands.lookup_customer import lookup_customer
from app.application.commands.update_consent import update_consent
from app.application.commands.update_customer import update_customer
from app.domain.enums import ConsentChannel, CustomerStatus
from app.domain.exceptions import (
    CustomerNotFoundError,
    DuplicateEmailError,
    VersionConflictError,
)
from app.infrastructure.database.repositories import InMemoryCustomerRepository


@pytest.fixture
def repo() -> InMemoryCustomerRepository:
    return InMemoryCustomerRepository()


def test_seed_customer_exists(repo: InMemoryCustomerRepository) -> None:
    customer = get_customer(repo, "C001")
    assert customer.email == "an@example.com"
    assert customer.status == CustomerStatus.ACTIVE
    assert customer.resource_version == 1


def test_create_customer_assigns_incrementing_id(repo: InMemoryCustomerRepository) -> None:
    customer = create_customer(repo, "Le Thi C", "c@example.com", "0911111111")
    assert customer.id == "C002"
    assert repo.get("C002") is not None


def test_create_customer_rejects_duplicate_email(repo: InMemoryCustomerRepository) -> None:
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


def test_update_customer_changes_fields_and_bumps_version(
    repo: InMemoryCustomerRepository,
) -> None:
    updated = update_customer(repo, "C001", expected_version=1, name="Nguyen Van An 2")
    assert updated.name == "Nguyen Van An 2"
    assert updated.email == "an@example.com"  # khong doi vi khong truyen
    assert updated.resource_version == 2  # tang sau moi lan sua thanh cong


def test_update_customer_not_found_raises(repo: InMemoryCustomerRepository) -> None:
    with pytest.raises(CustomerNotFoundError):
        update_customer(repo, "C999", expected_version=1, name="Ai do")


def test_update_customer_wrong_version_raises_conflict(
    repo: InMemoryCustomerRepository,
) -> None:
    """Mo phong 2 request PUT gan nhu dong thoi: request thu 2 dung
    If-Match cu (van con version=1) sau khi request thu 1 da thanh cong
    (version da len 2) - phai bi tu choi 409, khong duoc ghi de."""
    update_customer(repo, "C001", expected_version=1, name="Sua lan 1")
    with pytest.raises(VersionConflictError):
        update_customer(repo, "C001", expected_version=1, name="Sua lan 2 - phai bi chan")


def test_deactivate_customer_sets_inactive_and_bumps_version(
    repo: InMemoryCustomerRepository,
) -> None:
    customer = deactivate_customer(repo, "C001", expected_version=1)
    assert customer.status == CustomerStatus.INACTIVE
    assert customer.resource_version == 2
    assert repo.get("C001").status == CustomerStatus.INACTIVE  # type: ignore[union-attr]


def test_lookup_customer_by_email_returns_match(repo: InMemoryCustomerRepository) -> None:
    found = lookup_customer(repo, email="an@example.com", phone=None)
    assert found.id == "C001"


def test_lookup_customer_by_phone_returns_match(repo: InMemoryCustomerRepository) -> None:
    found = lookup_customer(repo, email=None, phone="0901234567")
    assert found.id == "C001"


def test_lookup_customer_not_found_raises(repo: InMemoryCustomerRepository) -> None:
    with pytest.raises(CustomerNotFoundError):
        lookup_customer(repo, email="khong-ton-tai@example.com", phone=None)


def test_update_consent_grants_channel(repo: InMemoryCustomerRepository) -> None:
    update_consent(repo, "C001", ConsentChannel.EMAIL, granted=True)
    assert repo._consents[("C001", "EMAIL")] is True  # type: ignore[attr-defined]


def test_update_consent_not_found_raises(repo: InMemoryCustomerRepository) -> None:
    with pytest.raises(CustomerNotFoundError):
        update_consent(repo, "C999", ConsentChannel.EMAIL, granted=True)
