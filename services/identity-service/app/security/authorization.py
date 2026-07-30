"""Central deny-by-default role authorization policy."""

from __future__ import annotations

from collections.abc import Callable

from app.domain.exceptions import Forbidden
from app.domain.value_objects import Principal


def require_any_role(*allowed_roles: str) -> Callable[[Principal], Principal]:
    allowed = frozenset(allowed_roles)
    if not allowed:
        raise ValueError("At least one allowed role is required")

    def authorize(principal: Principal) -> Principal:
        if allowed.isdisjoint(principal.roles):
            raise Forbidden()
        return principal

    return authorize
