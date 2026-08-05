"""Ticket command role authorization based on verified Service JWT claims."""

from app.domain.exceptions import Forbidden
from app.domain.value_objects import RequestContext


def authorize_check_in(context: RequestContext) -> str:
    if not ({"SERVICE", "CHECKIN_STAFF"} & context.actor_roles):
        raise Forbidden("CHECKIN_STAFF or SERVICE role is required")
    return context.actor_id or context.caller_service
