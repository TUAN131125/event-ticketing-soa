from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import httpx


class AggregateHealthService:
    CRITICAL = {"customer", "event", "seat", "booking", "payment", "ticket"}
    NONCRITICAL = {"notification", "realtime"}

    def __init__(
        self,
        registry: Any,
        repository: Any | None = None,
        timeout_seconds: float = 2.0,
    ) -> None:
        self.registry = registry
        self.repository = repository
        self.timeout_seconds = timeout_seconds

    async def check(self) -> tuple[int, dict[str, Any]]:
        names = sorted(self.CRITICAL | self.NONCRITICAL)
        probes = [self._probe_service(name) for name in names]
        if self.repository is not None:
            probes.append(self._probe_database())

        results = await asyncio.gather(*probes)
        critical_down = any(
            result["critical"] and result["status"] == "DOWN"
            for result in results
        )
        any_down = any(result["status"] == "DOWN" for result in results)
        status = "DOWN" if critical_down else "DEGRADED" if any_down else "UP"
        return (503 if critical_down else 200), {
            "status": status,
            "checkedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "dependencies": results,
        }


    async def ready(self) -> tuple[int, dict[str, Any]]:
        """Check only ESB-owned readiness, not provider availability."""

        if self.repository is None:
            return 200, {
                "status": "READY",
                "service": "booking-orchestrator",
                "version": "2.0.0",
            }
        result = await self._probe_database()
        ready = result["status"] == "UP"
        return (200 if ready else 503), {
            "status": "READY" if ready else "NOT_READY",
            "service": "booking-orchestrator",
            "version": "2.0.0",
        }

    async def _probe_service(self, name: str) -> dict[str, Any]:
        endpoint = self.registry.resolve(name)
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(endpoint.readiness_url)
                response.raise_for_status()
            return self._up(name + "-service", name in self.CRITICAL, started)
        except httpx.TimeoutException:
            code = "TIMEOUT"
        except httpx.HTTPStatusError:
            code = "NOT_READY"
        except Exception:
            code = "UNREACHABLE"
        return self._down(name + "-service", name in self.CRITICAL, started, code)

    async def _probe_database(self) -> dict[str, Any]:
        started = time.monotonic()
        try:
            await asyncio.wait_for(
                self.repository.list_by_status("STARTED", limit=1),
                timeout=self.timeout_seconds,
            )
            return self._up("database", True, started)
        except asyncio.TimeoutError:
            code = "TIMEOUT"
        except Exception:
            code = "NOT_READY"
        return self._down("database", True, started, code)

    @staticmethod
    def _up(name: str, critical: bool, started: float) -> dict[str, Any]:
        return {
            "name": name,
            "critical": critical,
            "status": "UP",
            "latencyMs": int((time.monotonic() - started) * 1000),
        }

    @staticmethod
    def _down(
        name: str,
        critical: bool,
        started: float,
        error_code: str,
    ) -> dict[str, Any]:
        return {
            "name": name,
            "critical": critical,
            "status": "DOWN",
            "latencyMs": int((time.monotonic() - started) * 1000),
            "errorCode": error_code,
        }
