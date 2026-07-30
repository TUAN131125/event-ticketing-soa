"""Closed request schemas."""

from pydantic import Field, SecretStr

from app.domain.enums import RoleAction, RoleName
from app.schemas.common import ClosedModel


class RegisterRequest(ClosedModel):
    email: str = Field(min_length=3, max_length=320)
    password: SecretStr = Field(min_length=12, max_length=128)


class LoginRequest(ClosedModel):
    email: str = Field(min_length=3, max_length=320)
    password: SecretStr = Field(min_length=12, max_length=128)


class RoleChangeRequest(ClosedModel):
    role: RoleName
    action: RoleAction
