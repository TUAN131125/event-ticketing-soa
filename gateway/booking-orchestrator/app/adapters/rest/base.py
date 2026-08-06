from __future__ import annotations

import time
from typing import Any

import httpx

from app.domain.errors import EsbError
from app.domain.models import RequestContext
from app.resilience.policies import ResiliencePolicy


class RestClient:
    def __init__(
        self,
        name: str,
        base_url: str,
        policy: ResiliencePolicy,
        credentials=None,
        audience: str | None = None,
        dependency_timeout_seconds: float = 4.0,
    ) -> None:
        self.name = name
        self.base = base_url.rstrip("/")
        self.policy = policy
        self.credentials = credentials
        self.audience = audience or name
        self.dependency_timeout_seconds = dependency_timeout_seconds

    def _service_token(self) -> str:
        if self.credentials is None:
            return ""
        if isinstance(self.credentials, str):
            return self.credentials
        token = getattr(self.credentials, "token", None)
        return str(token(self.audience)) if token is not None else ""

    async def request(
        self,
        method: str,
        path: str,
        ctx: RequestContext,
        *,
        json: dict | None = None,
        content: bytes | None = None,
        params: dict | None = None,
        headers: dict | None = None,
        idempotent: bool = False,
    ) -> Any:
        if json is not None and content is not None:
            raise ValueError("json and content cannot both be supplied")

        request_headers = {
            "X-Correlation-ID": ctx.correlation_id,
            "traceparent": ctx.traceparent,
        }
        request_headers.update(headers or {})

        async def call() -> Any:
            attempt_headers = dict(request_headers)
            service_token = self._service_token()
            if service_token:
                attempt_headers["Authorization"] = f"Bearer {service_token}"
            async with httpx.AsyncClient(timeout=None, follow_redirects=False) as client:
                response = await client.request(
                    method,
                    self.base + path,
                    json=json,
                    content=content,
                    params=params,
                    headers=attempt_headers,
                )
                if response.status_code >= 400:
                    body = self._safe_body(response)
                    error = body.get("error", body)
                    code = str(
                        error.get("code")
                        or error.get("errorCode")
                        or "DEPENDENCY_ERROR"
                    )
                    message = str(
                        error.get("message")
                        or self._validation_message(body)
                        or f"{self.name} returned {response.status_code}"
                    )
                    raise EsbError(
                        code,
                        message,
                        response.status_code,
                        response.status_code >= 500,
                        body,
                    )
                if response.status_code == 204 or not response.content:
                    return {}
                try:
                    return response.json()
                except ValueError as exc:
                    raise EsbError(
                        "INVALID_PROVIDER_RESPONSE",
                        f"{self.name} returned invalid JSON",
                        502,
                        True,
                    ) from exc

        mode = (
            "safe_read"
            if method.upper() in {"GET", "HEAD"}
            else "idempotent_command" if idempotent else "side_effect"
        )
        dependency_deadline = min(
            ctx.deadline_monotonic,
            time.monotonic() + self.dependency_timeout_seconds,
        )
        return await self.policy.execute(
            self.name,
            call,
            mode=mode,
            deadline=dependency_deadline,
        )

    @staticmethod
    def _safe_body(response: httpx.Response) -> dict[str, Any]:
        try:
            value = response.json()
            return value if isinstance(value, dict) else {"details": value}
        except ValueError:
            return {"message": response.text[:500]}

    @staticmethod
    def _validation_message(body: dict[str, Any]) -> str | None:
        detail = body.get("detail")
        if not isinstance(detail, list) or not detail:
            return None
        messages = [str(item.get("msg")) for item in detail if isinstance(item, dict)]
        return "; ".join(message for message in messages if message) or None
