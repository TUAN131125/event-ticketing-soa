"""Pydantic request schema - tang bien doi du lieu vao/ra HTTP."""
from typing import Optional

from pydantic import BaseModel, EmailStr


class CustomerCreateRequest(BaseModel):
    name: str
    email: EmailStr
    phone: str


class CustomerUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
