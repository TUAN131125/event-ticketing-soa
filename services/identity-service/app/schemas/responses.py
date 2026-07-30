"""Public response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.domain.entities import RoleChange, TokenPair, UserView
from app.schemas.common import ClosedModel


class UserResponse(ClosedModel):
    user_id: str = Field(alias="userId")
    email: str
    status: str
    roles: list[str]
    token_version: int = Field(alias="tokenVersion")
    created_at: datetime = Field(alias="createdAt")

    @classmethod
    def from_view(cls, user: UserView) -> UserResponse:
        return cls(
            userId=user.user_id,
            email=user.email,
            status=user.status,
            roles=list(user.roles),
            tokenVersion=user.token_version,
            createdAt=user.created_at,
        )


class TokenResponse(ClosedModel):
    access_token: str = Field(alias="accessToken")
    token_type: str = Field(default="Bearer", alias="tokenType")
    expires_in: int = Field(alias="expiresIn")
    csrf_token: str = Field(alias="csrfToken")
    user: UserResponse

    @classmethod
    def from_pair(cls, pair: TokenPair, csrf_token: str) -> TokenResponse:
        return cls(
            accessToken=pair.access_token,
            tokenType="Bearer",
            expiresIn=pair.access_expires_in,
            csrfToken=csrf_token,
            user=UserResponse.from_view(pair.user),
        )


class RoleChangeResponse(ClosedModel):
    user: UserResponse
    role: str
    action: str
    changed: bool

    @classmethod
    def from_result(cls, result: RoleChange) -> RoleChangeResponse:
        return cls(
            user=UserResponse.from_view(result.user),
            role=result.role,
            action=result.action,
            changed=result.changed,
        )


class LogoutResponse(ClosedModel):
    status: str = "LOGGED_OUT"
