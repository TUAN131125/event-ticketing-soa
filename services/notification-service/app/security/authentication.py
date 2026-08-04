"""Xac thuc Bearer JWT cho cac endpoint Admin/Ops (GET/POST /deliveries*,
PUT /templates/*) - theo dung quy uoc RS256 + JWKS da dung trong
Identity Service (app/security/tokens.py ben identity-service): notification-
service KHONG tu phat hanh token, chi xac minh chu ky bang public key
(RS256) cua Identity Service, kem kiem tra issuer/audience/exp.

Public key duoc nap tu file (NOTIFICATION_JWT_PUBLIC_KEY_PATH) - trong
Docker Compose, mount cung file public key ma identity-service dang dung
(vd volume dung chung `./keys/identity-public.pem`) vao ca 2 container.
"""
from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, Header
from jwt import InvalidTokenError

from app.config import Settings, get_settings
from app.domain.exceptions import NotificationDomainError


class UnauthorizedError(NotificationDomainError):
    code = "UNAUTHORIZED"
    http_status = 401
    retryable = False


class ForbiddenError(NotificationDomainError):
    code = "FORBIDDEN"
    http_status = 403
    retryable = False


@dataclass(frozen=True)
class Principal:
    user_id: str
    roles: tuple[str, ...]


def _decode(token: str, settings: Settings) -> Principal:
    if settings.jwt_public_key is None:
        # Chua cau hinh public key (vd moi tro local, chua mount key that)
        # - tu choi ro rang thay vi am tham bo qua xac thuc.
        raise UnauthorizedError("Chua cau hinh NOTIFICATION_JWT_PUBLIC_KEY_PATH")
    try:
        payload = jwt.decode(
            token,
            settings.jwt_public_key,
            algorithms=["RS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "roles", "exp", "iss", "aud"]},
        )
    except InvalidTokenError as exc:
        raise UnauthorizedError(f"Token khong hop le: {exc}") from exc
    roles = payload.get("roles") or []
    if not isinstance(roles, list):
        raise UnauthorizedError("Claim roles khong hop le")
    return Principal(user_id=str(payload["sub"]), roles=tuple(roles))


def require_principal(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Thieu header Authorization: Bearer <token>")
    token = authorization.split(" ", 1)[1].strip()
    return _decode(token, settings)


def require_role(*allowed_roles: str):
    """Dependency factory: dung cho endpoint Admin/Ops (NOT-05/07/08/09) -
    yeu cau it nhat 1 trong cac role duoc phep."""

    def _dependency(principal: Principal = Depends(require_principal)) -> Principal:
        if not set(principal.roles) & set(allowed_roles):
            raise ForbiddenError(
                f"Can 1 trong cac role {allowed_roles}, hien co {principal.roles}"
            )
        return principal

    return _dependency
