"""Fixtures for suites that drive the running Compose stack."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tests.support.e2e import (  # noqa: E402
    REQUEST_TIMEOUT,
    Browser,
    E2EError,
    Inventory,
    provision_inventory,
    register_browser_user,
    require_stack,
)


@pytest.fixture(scope="session")
def stack() -> None:
    try:
        require_stack()
    except E2EError as exc:
        pytest.fail(str(exc), pytrace=False)


@pytest.fixture()
def client(stack: None) -> Iterator[httpx.Client]:
    with httpx.Client(timeout=REQUEST_TIMEOUT) as value:
        yield value


@pytest.fixture()
def browser(client: httpx.Client) -> Browser:
    return register_browser_user(client)


@pytest.fixture()
def other_browser(client: httpx.Client) -> Browser:
    return register_browser_user(client)


@pytest.fixture()
def inventory(client: httpx.Client) -> Inventory:
    """A dedicated Event and seat map so every test is independent and repeatable."""
    return provision_inventory(client, seat_count=4)
