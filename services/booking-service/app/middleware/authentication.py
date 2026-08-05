"""Service JWT authentication for internal Booking API calls."""

from typing import Annotated

from fastapi import Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from libs.platform_security import ServiceAuthenticationError

from app.domain.exceptions import AuthenticationFailed
from app.domain.value_objects import RequestContext
from app.security.input_validation import safe_identifier

SERVICE_JWT = HTTPBearer(auto_error=False, scheme_name="ServiceJwt")


def require_internal_caller(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(SERVICE_JWT)],
) -> RequestContext:
    try:
        authorization = (
            f"Bearer {credentials.credentials}" if credentials is not None else None
        )
        principal = request.app.state.service_jwt_verifier.verify_authorization(
            authorization
        )
    except ServiceAuthenticationError as exc:
        raise AuthenticationFailed() from exc
    return RequestContext(
        correlation_id=safe_identifier(getattr(request.state, "correlation_id", None)),
        caller_service=principal.subject,
    )
