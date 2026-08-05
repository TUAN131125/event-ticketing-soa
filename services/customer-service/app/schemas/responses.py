"""Pydantic response schema."""
from __future__ import annotations

from pydantic import BaseModel

from app.domain.entities import Customer


class CustomerResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: str
    status: str
    createdAt: str

    @classmethod
    def from_entity(cls, customer: Customer) -> CustomerResponse:
        return cls(
            id=customer.id,
            name=customer.name,
            email=customer.email,
            phone=customer.phone,
            status=customer.status.value,
            createdAt=customer.created_at.isoformat(),
        )
