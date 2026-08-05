"""Canonical Customer response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import Customer, IdentityMapping


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CustomerResponse(ResponseModel):
    customer_id: str = Field(alias="customerId")
    name: str
    email: str
    phone: str | None = None
    status: Literal["ACTIVE", "INACTIVE", "ANONYMIZED"]
    resource_version: int = Field(alias="resourceVersion", ge=1)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    @classmethod
    def from_entity(cls, customer: Customer) -> CustomerResponse:
        return cls(
            customerId=customer.id,
            name=customer.name,
            email=customer.email,
            phone=customer.phone,
            status=customer.status.value,
            resourceVersion=customer.resource_version,
            createdAt=customer.created_at,
            updatedAt=customer.updated_at,
        )


class IdentityMappingResponse(ResponseModel):
    identity_subject: str = Field(alias="identitySubject")
    customer_id: str = Field(alias="customerId")
    status: Literal["ACTIVE", "INACTIVE", "UNLINKED"]
    resource_version: int = Field(alias="resourceVersion", ge=1)
    linked_at: datetime = Field(alias="linkedAt")
    updated_at: datetime = Field(alias="updatedAt")

    @classmethod
    def from_entity(cls, mapping: IdentityMapping) -> IdentityMappingResponse:
        return cls(
            identitySubject=mapping.identity_subject,
            customerId=mapping.customer_id,
            status=cast(Literal["ACTIVE", "INACTIVE", "UNLINKED"], mapping.status),
            resourceVersion=mapping.resource_version,
            linkedAt=mapping.linked_at,
            updatedAt=mapping.updated_at,
        )
