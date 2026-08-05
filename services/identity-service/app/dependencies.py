"""FastAPI dependencies and centralized authentication policy."""

from __future__ import annotations

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer

from app.application.service import IdentityService
from app.domain.exceptions import Forbidden, Unauthenticated
from app.domain.value_objects import Principal, RequestContext

browser_bearer = HTTPBearer(
    scheme_name="BrowserBearerAuth",
    auto_error=False,
)
refresh_cookie = APIKeyCookie(
    scheme_name="RefreshCookie",
    name="identity_refresh",
    auto_error=False,
)


def get_context(request: Request) -> RequestContext:
    context = getattr(request.state, "identity_context", None)
    if not isinstance(context, RequestContext):
        raise RuntimeError("request context middleware is not installed")
    return context


def get_service(request: Request) -> IdentityService:
    service = getattr(request.app.state, "identity_service", None)
    if not isinstance(service, IdentityService):
        raise RuntimeError("identity service is not initialized")
    return service


def current_principal(
    credentials: HTTPAuthorizationCredentials | None = Security(browser_bearer),
    service: IdentityService = Depends(get_service),
) -> Principal:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise Unauthenticated()
    return service.authenticate_access_token(credentials.credentials)


def admin_principal(principal: Principal = Depends(current_principal)) -> Principal:
    if "ADMIN" not in principal.roles:
        raise Forbidden()
    return principal
