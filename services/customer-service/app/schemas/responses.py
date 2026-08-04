"""Pydantic response schema - ten field khop dung schema Customer trong
contracts/openapi/customer-service.yaml (customerId, resourceVersion,
createdAt, updatedAt)."""
from __future__ import annotations

from pydantic import BaseModel

from app.domain.entities import Customer


class CustomerResponse(BaseModel):
    customerId: str
    name: str
    email: str
    phone: str | None
    status: str
    resourceVersion: int
    createdAt: str
    updatedAt: str

    @classmethod
    def from_entity(cls, customer: Customer) -> "CustomerResponse":
        return cls(
            customerId=customer.id,
            name=customer.name,
            email=customer.email,
            phone=customer.phone,
            status=customer.status.value,
            resourceVersion=customer.resource_version,
            createdAt=customer.created_at.isoformat(),
            updatedAt=customer.updated_at.isoformat(),
        )
