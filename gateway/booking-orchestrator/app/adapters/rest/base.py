from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any

import httpx

from app.domain.errors import (
    AmbiguousOutcome,
    BusinessFault,
    DependencyFailure,
    EsbError,
)
from app.domain.models import RequestContext
from app.ports.repositories import TraceRepository
from app.resilience.policies import ResilienceExecutor, RetryClass
from app.security.jwt import JwtSigner

logger = logging.getLogger(__name__)


class RestClient:
    def __init__(
        self,
        base_url: str,
        audience: str,
        http: httpx.AsyncClient,
        signer: JwtSigner,
        resilience: ResilienceExecutor,
        traces: TraceRepository | None = None,
    ) -> None:
        self.base_url, self.audience, self.http, self.signer, self.resilience = (
            base_url.rstrip("/"),
            audience,
            http,
            signer,
            resilience,
        )
        self.traces = traces

    async def request(
        self,
        method: str,
        path: str,
        context: RequestContext,
        *,
        json_body: Mapping[str, Any] | None = None,
        raw_body: bytes | None = None,
        idempotency_key: str | None = None,
        retry_class: RetryClass = RetryClass.NONE,
        ambiguous_command: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> Any:
        headers = {
            "Authorization": f"Bearer {self.signer.service_token(self.audience)}",
            "X-Correlation-ID": context.correlation_id,
        }
        if context.trace_id:
            headers["traceparent"] = context.trace_id
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        headers.update(extra_headers or {})

        async def invoke() -> Any:
            try:
                if raw_body is not None:
                    response = await self.http.request(method, f"{self.base_url}{path}", content=raw_body, headers=headers)
                else:
                    response = await self.http.request(method, f"{self.base_url}{path}", json=json_body, headers=headers)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if ambiguous_command:
                    raise AmbiguousOutcome(path) from exc
                raise DependencyFailure("DEPENDENCY_UNAVAILABLE", "Dependency is unavailable.", 503, True) from exc
            if response.status_code >= 400:
                error = self._safe_error(response)
                if 400 <= response.status_code < 500:
                    raise BusinessFault(
                        error["code"],
                        error["message"],
                        response.status_code,
                        bool(error["retryable"]),
                        error.get("details", {}),
                    )
                raise DependencyFailure(error["code"], error["message"], 503, True, error.get("details", {}))
            if response.status_code == 204:
                return {}
            try:
                return response.json()
            except ValueError as exc:
                raise DependencyFailure(
                    "INVALID_PROVIDER_RESPONSE",
                    "Dependency returned an invalid response.",
                    503,
                    True,
                ) from exc

        started = time.perf_counter()
        try:
            result = await self.resilience.execute(invoke, retry_class, context)
        except EsbError as exc:
            await self._observe(path, context, "FAILURE", started, exc.code)
            raise
        except Exception:
            await self._observe(path, context, "FAILURE", started, "DEPENDENCY_UNAVAILABLE")
            raise
        await self._observe(path, context, "SUCCESS", started)
        return result

    async def _observe(
        self,
        operation: str,
        context: RequestContext,
        outcome: str,
        started: float,
        error_code: str | None = None,
    ) -> None:
        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        fields = {
            "correlationId": context.correlation_id,
            "traceId": context.trace_id,
            "workflowId": context.workflow_id,
            "operation": operation,
            "provider": self.audience,
            "step": operation,
            "outcome": outcome,
            "duration": duration_ms,
        }
        logger.info("provider_call", extra=fields)
        if self.traces is not None:
            try:
                await self.traces.append(
                    context.correlation_id,
                    self.audience,
                    operation,
                    outcome,
                    duration_ms,
                    error_code,
                )
            except Exception as exc:  # noqa: BLE001 -- telemetry failure must not fail a provider call
                logger.warning(
                    "trace_persistence_failed",
                    extra={
                        **fields,
                        "outcome": "TRACE_WRITE_FAILED",
                        "errorType": type(exc).__name__,
                    },
                )

    @staticmethod
    def _safe_error(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
            error = body.get("error", {})
            return {
                "code": str(error.get("code", "DEPENDENCY_ERROR")),
                "message": str(error.get("message", "Dependency request failed.")),
                "retryable": bool(error.get("retryable", False)),
                "details": error.get("details", {}),
            }
        except (ValueError, AttributeError):
            return {
                "code": "DEPENDENCY_ERROR",
                "message": "Dependency request failed.",
                "retryable": response.status_code >= 500,
            }
