"""Closed request schemas."""

from typing import Literal

from pydantic import EmailStr, Field, SecretStr

from app.schemas.common import ClosedModel, Role


class RegisterRequest(ClosedModel):
    email: EmailStr = Field(max_length=320)
    password: SecretStr = Field(min_length=12, max_length=128)


class LoginRequest(ClosedModel):
    email: EmailStr = Field(max_length=320)
    password: SecretStr = Field(min_length=12, max_length=128)


class RoleChangeRequest(ClosedModel):
    role: Role
    action: Literal["ASSIGN", "REVOKE"]
