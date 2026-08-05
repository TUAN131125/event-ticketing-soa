"""Pydantic request schema - tang bien doi du lieu vao/ra HTTP."""

from pydantic import BaseModel, EmailStr


class CustomerCreateRequest(BaseModel):
    name: str
    email: EmailStr
    phone: str


class CustomerUpdateRequest(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
