"""Public response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from pydantic import EmailStr, Field

from app.domain.entities import RoleChange, TokenPair, UserView
from app.schemas.common import ClosedModel, Role


class User(ClosedModel):
    user_id: UUID = Field(alias="userId")
    email: EmailStr
    status: Literal["ACTIVE", "DISABLED"]
    roles: list[Role] = Field(json_schema_extra={"uniqueItems": True})
    token_version: int = Field(alias="tokenVersion", ge=1)
    created_at: datetime = Field(alias="createdAt")

    @classmethod
    def from_view(cls, user: UserView) -> User:
        return cls(
            userId=UUID(user.user_id),
            email=user.email,
            status=cast(Literal["ACTIVE", "DISABLED"], user.status),
            roles=[Role(value) for value in user.roles],
            tokenVersion=user.token_version,
            createdAt=user.created_at,
        )


class TokenResponse(ClosedModel):
    access_token: str = Field(
        alias="accessToken", min_length=1, json_schema_extra={"readOnly": True}
    )
    token_type: Literal["Bearer"] = Field(default="Bearer", alias="tokenType")
    expires_in: int = Field(alias="expiresIn", ge=1)
    csrf_token: str = Field(
        alias="csrfToken", min_length=32, json_schema_extra={"readOnly": True}
    )
    user: User

    @classmethod
    def from_pair(cls, pair: TokenPair, csrf_token: str) -> TokenResponse:
        return cls(
            accessToken=pair.access_token,
            tokenType="Bearer",
            expiresIn=pair.access_expires_in,
            csrfToken=csrf_token,
            user=User.from_view(pair.user),
        )


class RoleChangeResponse(ClosedModel):
    user: User
    role: Role
    action: Literal["ASSIGN", "REVOKE"]
    changed: bool

    @classmethod
    def from_result(cls, result: RoleChange) -> RoleChangeResponse:
        return cls(
            user=User.from_view(result.user),
            role=Role(result.role),
            action=result.action.value,
            changed=result.changed,
        )


class Jwk(ClosedModel):
    kty: Literal["RSA"]
    use: Literal["sig"]
    alg: Literal["RS256"]
    kid: str
    n: str
    e: str


class JwkSet(ClosedModel):
    keys: list[Jwk]
