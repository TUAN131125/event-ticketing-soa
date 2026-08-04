"""Pydantic request schema - tang bien doi du lieu vao/ra HTTP.
Ten field va rang buoc khop voi contracts/openapi/customer-service.yaml."""
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.domain.enums import ConsentChannel


class CustomerCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    email: EmailStr = Field(max_length=254)
    phone: Optional[str] = Field(default=None, max_length=30)


class CustomerUpdateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    phone: Optional[str] = None


class ConsentUpdateRequest(BaseModel):
    channel: ConsentChannel
    granted: bool
