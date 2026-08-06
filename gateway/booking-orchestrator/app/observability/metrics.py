from __future__ import annotations

import threading
from collections import Counter, defaultdict
from typing import Any


class Metrics:
    """Small dependency-free Prometheus text collector for the lab runtime."""

    def __init__(self) -> None:
        self._counters: Counter[str] = Counter()
        self._observations: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def inc(self, name: str, **labels: Any) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] += 1

    def observe(self, name: str, value: float, **labels: Any) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._observations[key].append(float(value))

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            for key, value in sorted(self._counters.items()):
                lines.append(f"{key} {value}")
            for key, values in sorted(self._observations.items()):
                lines.append(f"{key}_count {len(values)}")
                lines.append(f"{key}_sum {sum(values)}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _key(name: str, labels: dict[str, Any]) -> str:
        if not labels:
            return name
        rendered = ",".join(
            f'{key}="{str(value).replace(chr(34), chr(92) + chr(34))}"'
            for key, value in sorted(labels.items())
        )
        return f"{name}{{{rendered}}}"
