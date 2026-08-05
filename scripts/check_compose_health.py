"""Fail unless every Compose application container is running and healthy."""

from __future__ import annotations

import json
import sys
from typing import Any


def records(lines: list[str]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for line in lines:
        value = line.strip()
        if value:
            parsed.append(json.loads(value))
    if not parsed:
        raise ValueError("docker compose ps returned no containers")
    return parsed


def main() -> int:
    try:
        containers = records(sys.stdin.readlines())
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"Compose health output is invalid: {exc}", file=sys.stderr)
        return 2
    unhealthy = [
        item.get("Service", item.get("Name", "unknown"))
        for item in containers
        if item.get("State") != "running"
        or (item.get("Health") not in {None, "", "healthy"})
    ]
    if unhealthy:
        print(
            f"Containers not ready: {', '.join(map(str, unhealthy))}", file=sys.stderr
        )
        return 1
    print(f"Ready containers: {len(containers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
