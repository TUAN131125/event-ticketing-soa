"""One HTTP readiness probe reused for every dependency, REST or SOAP.

Providers publish an unauthenticated `GET /health/ready`, so a single probe serves all
of them. The probe deliberately bypasses the retry and circuit-breaker executor: a
health request must report what is true now, not a cached breaker verdict, and must
never retry inside one request.
"""

from __future__ import annotations

import httpx

from app.domain.errors import ProbeFailure


class ReadinessProbe:
    def __init__(self, name: str, base_url: str, http: httpx.AsyncClient, *, critical: bool) -> None:
        self.name = name
        self.critical = critical
        # Readiness always sits at the service origin. Some configured URLs point at a
        # sub-path (the Seat SOAP endpoint), so the path is dropped rather than appended.
        origin = httpx.URL(base_url).copy_with(path="/", query=None, fragment=None)
        self._url = str(origin.join("health/ready"))
        self._http = http

    async def check(self, timeout_seconds: float) -> None:
        try:
            response = await self._http.get(self._url, timeout=timeout_seconds)
        except httpx.TimeoutException as exc:
            raise ProbeFailure("TIMEOUT") from exc
        except httpx.HTTPError as exc:
            raise ProbeFailure("UNREACHABLE") from exc
        if response.status_code != 200:
            raise ProbeFailure("NOT_READY")
