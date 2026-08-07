"""Service JWT authentication for internal Booking API calls.

The caller's identity comes from the signed `sub` claim, never from a header the caller
controls. X-Actor-ID remains a non-authoritative audit hint only.
"""

from typing import Annotated, cast

from fastapi import Header, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from libs.platform_security import ServiceAuthenticationError, ServicePrincipal

from app.domain.rules import validate_identifier
from app.domain.value_objects import RequestContext
from app.security.input_validation import safe_identifier

SERVICE_JWT = HTTPBearer(auto_error=False, scheme_name="ServiceJwt")


def require_internal_caller(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(SERVICE_JWT)],
    x_actor_id: str | None = Header(default=None, alias="X-Actor-ID"),
) -> RequestContext:
    authorization = (
        f"Bearer {credentials.credentials}" if credentials is not None else None
    )
    try:
        principal = cast(
            ServicePrincipal,
            request.app.state.service_jwt_verifier.verify_authorization(authorization),
        )
    except ServiceAuthenticationError as exc:
        # No cryptographic detail and no token material reaches the response or the log.
        raise HTTPException(
            status_code=401, detail="Service authentication failed"
        ) from exc

    correlation_id = safe_identifier(getattr(request.state, "correlation_id", None))
    return RequestContext(
        correlation_id=correlation_id,
        caller_service=validate_identifier(principal.subject, "callerService"),
        actor_id=(validate_identifier(x_actor_id, "actorId") if x_actor_id else None),
    )
