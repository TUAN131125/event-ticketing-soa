"""Customer-owned identity mapping commands and query."""

from datetime import UTC, datetime

from app.domain.entities import IdentityMapping
from app.domain.enums import CustomerStatus
from app.domain.exceptions import (
    CustomerNotFoundError,
    IdentityMappingConflictError,
    PreconditionFailedError,
)
from app.repositories.interfaces import CustomerRepository


def link_identity(
    repo: CustomerRepository,
    customer_id: str,
    identity_subject: str,
    expected_version: int,
) -> IdentityMapping:
    customer = repo.get(customer_id)
    if customer is None:
        raise CustomerNotFoundError(customer_id)
    if customer.resource_version != expected_version:
        raise PreconditionFailedError("Customer resource version does not match")
    existing_subject = repo.get_identity_mapping(identity_subject)
    existing_customer = repo.get_identity_mapping_by_customer(customer_id)
    if (
        existing_subject is not None
        and existing_subject.customer_id != customer_id
        and existing_subject.status != "UNLINKED"
    ) or (
        existing_customer is not None
        and existing_customer.identity_subject != identity_subject
        and existing_customer.status != "UNLINKED"
    ):
        raise IdentityMappingConflictError("Identity is already linked")
    now = datetime.now(UTC)
    mapping = existing_subject or IdentityMapping(
        identity_subject=identity_subject,
        customer_id=customer_id,
        status="ACTIVE",
        resource_version=1,
        linked_at=now,
        updated_at=now,
    )
    if existing_subject is not None:
        mapping.customer_id = customer_id
        mapping.status = "ACTIVE"
        mapping.resource_version += 1
        mapping.updated_at = now
    repo.save_identity_mapping(mapping)
    return mapping


def unlink_identity(
    repo: CustomerRepository, customer_id: str, expected_version: int
) -> IdentityMapping:
    customer = repo.get(customer_id)
    if customer is None:
        raise CustomerNotFoundError(customer_id)
    mapping = repo.get_identity_mapping_by_customer(customer_id)
    if mapping is None:
        raise CustomerNotFoundError(customer_id)
    if mapping.resource_version != expected_version:
        raise PreconditionFailedError("Identity mapping version does not match")
    mapping.status = "UNLINKED"
    mapping.resource_version += 1
    mapping.updated_at = datetime.now(UTC)
    repo.save_identity_mapping(mapping)
    return mapping


def resolve_identity(
    repo: CustomerRepository, identity_subject: str
) -> IdentityMapping | None:
    mapping = repo.get_identity_mapping(identity_subject)
    if mapping is None or mapping.status == "UNLINKED":
        return None
    customer = repo.get(mapping.customer_id)
    if customer is None:
        return None
    if customer.status != CustomerStatus.ACTIVE:
        mapping.status = "INACTIVE"
    return mapping
