"""Value objects shared across transport and application layers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RequestContext:
    correlation_id: str
    trace_id: str
    client_ip: str
    user_agent: str | None


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    roles: tuple[str, ...]
    token_version: int
    token_id: str
