"""Authorization rules for sensitive ticket operations."""

import secrets

from app.domain.exceptions import AuthenticationFailed, Forbidden
from app.domain.value_objects import RequestContext

CHECK_IN_ROLES = frozenset({"CHECKIN_STAFF", "ADMIN"})


def authenticate_service(provided: str | None, expected: str) -> None:
    if not provided or not secrets.compare_digest(provided, expected):
        raise AuthenticationFailed()


def authorize_check_in(context: RequestContext) -> str:
    if context.actor_id is None or not context.actor_roles.intersection(CHECK_IN_ROLES):
        raise Forbidden("Check-in requires a CHECKIN_STAFF or ADMIN actor")
    return context.actor_id
