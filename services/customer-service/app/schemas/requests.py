"""Closed canonical Customer request schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CustomerCreateRequest(ClosedModel):
    name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)


class CustomerUpdateRequest(ClosedModel):
    name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    phone: str | None = None


class ConsentUpdateRequest(ClosedModel):
    channel: Literal["EMAIL", "SMS"]
    granted: bool


class IdentityLinkRequest(ClosedModel):
    identity_subject: str = Field(alias="identitySubject", min_length=1, max_length=128)
