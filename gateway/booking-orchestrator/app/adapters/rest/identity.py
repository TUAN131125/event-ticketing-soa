from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Mapping

import httpx

from app.domain.errors import DependencyError
from app.domain.models import RequestContext
from app.resilience.policies import ResiliencePolicy


_ALLOWED_PATHS = frozenset(
    {
        "/auth/register",
        "/auth/login",
        "/auth/refresh",
        "/auth/logout",
        "/auth/me",
    }
)
_FORWARD_REQUEST_HEADERS = frozenset(
    {
        "authorization",
        "content-type",
        "cookie",
        "idempotency-key",
        "x-csrf-token",
        "x-correlation-id",
        "traceparent",
        "user-agent",
    }
)
_FORWARD_RESPONSE_HEADERS = frozenset(
    {
        "cache-control",
        "pragma",
        "etag",
        "retry-after",
        "x-correlation-id",
        "x-trace-id",
    }
)


@dataclass(frozen=True, slots=True)
class IdentityProxyResponse:
    status_code: int
    content: bytes
    media_type: str
    headers: tuple[tuple[str, str], ...]
    set_cookies: tuple[str, ...]


class IdentityProxyAdapter:
    """Narrow browser-auth proxy for the canonical Identity public contract.

    The adapter deliberately does not use the ESB service credential. Identity remains
    authoritative for credentials, refresh sessions, roles and access-token issuance.
    The ESB only forwards the five approved authentication operations, preserves cookie
    semantics and normalizes transport failures at the gateway boundary.
    """

    def __init__(
        self,
        base_url: str,
        policy: ResiliencePolicy,
        dependency_timeout_seconds: float = 4.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.policy = policy
        self.dependency_timeout_seconds = dependency_timeout_seconds

    async def proxy(
        self,
        method: str,
        path: str,
        ctx: RequestContext,
        *,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        idempotent: bool = False,
    ) -> IdentityProxyResponse:
        if path not in _ALLOWED_PATHS:
            raise ValueError(f"Identity proxy path is not allowed: {path}")

        forwarded: dict[str, str] = {
            "Accept": "application/json",
            "X-Correlation-ID": ctx.correlation_id,
            "traceparent": ctx.traceparent,
        }
        for name, value in (headers or {}).items():
            if name.casefold() in _FORWARD_REQUEST_HEADERS and value:
                forwarded[name] = value

        async def call() -> IdentityProxyResponse:
            try:
                async with httpx.AsyncClient(timeout=None, follow_redirects=False) as client:
                    response = await client.request(
                        method,
                        self.base_url + path,
                        content=body,
                        headers=forwarded,
                    )
            except httpx.TimeoutException as exc:
                raise DependencyError(
                    "IDENTITY_TIMEOUT",
                    "Identity Service did not respond before the dependency deadline",
                    504,
                    True,
                ) from exc
            except httpx.TransportError as exc:
                raise DependencyError(
                    "IDENTITY_UNAVAILABLE",
                    "Identity Service is unavailable",
                    503,
                    True,
                ) from exc

            content_type = response.headers.get("content-type", "application/json")
            media_type = content_type.split(";", 1)[0].strip() or "application/json"
            response_headers = tuple(
                (name, value)
                for name, value in response.headers.multi_items()
                if name.casefold() in _FORWARD_RESPONSE_HEADERS
            )
            cookies = tuple(
                self._rewrite_cookie_path(value)
                for value in response.headers.get_list("set-cookie")
            )
            return IdentityProxyResponse(
                status_code=response.status_code,
                content=response.content,
                media_type=media_type,
                headers=response_headers,
                set_cookies=cookies,
            )

        mode = (
            "safe_read"
            if method.upper() in {"GET", "HEAD"}
            else "idempotent_command" if idempotent else "side_effect"
        )
        deadline = min(
            ctx.deadline_monotonic,
            time.monotonic() + self.dependency_timeout_seconds,
        )
        return await self.policy.execute(
            "identity",
            call,
            mode=mode,
            deadline=deadline,
        )

    @staticmethod
    def _rewrite_cookie_path(value: str) -> str:
        """Expose Identity's /auth cookies only under the ESB /api/auth façade."""

        parts = [part.strip() for part in value.split(";")]
        rewritten: list[str] = []
        saw_path = False
        for part in parts:
            if part.casefold().startswith("path="):
                rewritten.append("Path=/api/auth")
                saw_path = True
            elif part.casefold().startswith("domain="):
                # Never leak an internal service DNS name to the browser.
                continue
            else:
                rewritten.append(part)
        if not saw_path:
            rewritten.append("Path=/api/auth")
        return "; ".join(rewritten)
