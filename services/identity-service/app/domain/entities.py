"""Application result entities independent of HTTP."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import RoleAction


@dataclass(frozen=True, slots=True)
class UserView:
    user_id: str
    email: str
    status: str
    roles: tuple[str, ...]
    token_version: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_in: int
    refresh_expires_at: datetime
    user: UserView


@dataclass(frozen=True, slots=True)
class RoleChange:
    user: UserView
    role: str
    action: RoleAction
    changed: bool
