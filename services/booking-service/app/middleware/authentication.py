"""FastAPI dependency for service-to-service authentication."""

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
    description="Internal shared secret. Never forward a customer token here.",
    auto_error=False,
)


def require_internal_caller(
    request: Request,
    x_service_token: str | None = Security(SERVICE_TOKEN_HEADER),
    x_caller_service: str | None = Header(default=None, alias="X-Caller-Service"),
    x_actor_id: str | None = Header(default=None, alias="X-Actor-ID"),
) -> RequestContext:
    settings = request.app.state.settings
    authenticate_service(x_service_token, settings.service_token)
    if not x_caller_service:
        raise InvalidRequest("X-Caller-Service header is required")
    correlation_id = safe_identifier(getattr(request.state, "correlation_id", None))
    return RequestContext(
        correlation_id=correlation_id,
        caller_service=validate_identifier(x_caller_service, "callerService"),
        actor_id=(validate_identifier(x_actor_id, "actorId") if x_actor_id else None),
    )
