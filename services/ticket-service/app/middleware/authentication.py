"""FastAPI dependency for service authentication and actor context."""

from fastapi import Header, Request, Security
from fastapi.security import APIKeyHeader

from app.domain.exceptions import InvalidRequest
from app.domain.rules import validate_identifier
from app.domain.value_objects import RequestContext
from app.security.authorization import authenticate_service
from app.security.input_validation import safe_identifier

SERVICE_TOKEN_HEADER = APIKeyHeader(
    name="X-Service-Token",
    scheme_name="serviceToken",
    description="Internal shared secret. Never expose QR signing material here.",
    auto_error=False,
)


def require_internal_caller(
    request: Request,
    x_service_token: str | None = Security(SERVICE_TOKEN_HEADER),
    x_caller_service: str | None = Header(default=None, alias="X-Caller-Service"),
    x_actor_id: str | None = Header(default=None, alias="X-Actor-ID"),
    x_actor_roles: str | None = Header(default=None, alias="X-Actor-Roles"),
) -> RequestContext:
    settings = request.app.state.settings
    authenticate_service(x_service_token, settings.service_token)
    if not x_caller_service:
        raise InvalidRequest("X-Caller-Service header is required")
    roles = _parse_roles(x_actor_roles)
    correlation_id = safe_identifier(getattr(request.state, "correlation_id", None))
    return RequestContext(
        correlation_id=correlation_id,
        caller_service=validate_identifier(x_caller_service, "callerService"),
        actor_id=(validate_identifier(x_actor_id, "actorId") if x_actor_id else None),
        actor_roles=roles,
    )


def _parse_roles(value: str | None) -> frozenset[str]:
    if value is None or not value.strip():
        return frozenset()
    raw_roles = [part.strip().upper() for part in value.split(",")]
    if len(raw_roles) > 10 or any(not role for role in raw_roles):
        raise InvalidRequest("X-Actor-Roles is invalid")
    return frozenset(validate_identifier(role, "actorRole") for role in raw_roles)
