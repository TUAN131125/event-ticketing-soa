"""Client helpers for tests that drive the real Compose stack over HTTP and SOAP.

Every assertion in the integration and fault-injection suites goes through the running
containers. Fixtures may use canonical internal APIs to arrange state (an Event, a seat
map, a Customer identity mapping), but no test may substitute a fake provider, an
in-memory repository or a mock for the behaviour it asserts.
"""

from __future__ import annotations

import os
import subprocess
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from lxml import etree

from libs.platform_security import ServiceJwtSigner

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SEAT_NS = "urn:event-ticketing:seat:v1"
SOAP_ENV_NS = "http://schemas.xmlsoap.org/soap/envelope/"

ESB_URL = os.getenv("E2E_ESB_URL", "http://localhost:8000")
IDENTITY_URL = os.getenv("E2E_IDENTITY_URL", "http://localhost:8009")
CUSTOMER_URL = os.getenv("E2E_CUSTOMER_URL", "http://localhost:8001")
EVENT_URL = os.getenv("E2E_EVENT_URL", "http://localhost:8002")
SEAT_SOAP_URL = os.getenv("E2E_SEAT_SOAP_URL", "http://localhost:8003/soap")
NOTIFICATION_URL = os.getenv("E2E_NOTIFICATION_URL", "http://localhost:8007")
SIGNING_KEY_PATH = Path(
    os.getenv(
        "E2E_SERVICE_JWT_PRIVATE_KEY_PATH",
        str(REPOSITORY_ROOT / "local-secrets" / "esb-internal-private.pem"),
    )
)
SERVICE_JWT_ISSUER = os.getenv("E2E_SERVICE_JWT_ISSUER", "event-ticketing-internal")
SERVICE_JWT_KEY_ID = os.getenv("E2E_SERVICE_JWT_KEY_ID", "esb-internal-1")
REQUEST_TIMEOUT = float(os.getenv("E2E_REQUEST_TIMEOUT_SECONDS", "20"))
READINESS_TIMEOUT = float(os.getenv("E2E_READINESS_TIMEOUT_SECONDS", "120"))
POLL_INTERVAL = 0.5


class E2EError(AssertionError):
    """Raised with actionable context when the running stack cannot satisfy a test."""


def correlation_id(prefix: str) -> str:
    # The canonical RequiredCorrelationId parameter allows 16-64 characters.
    return f"{prefix}-{uuid.uuid4().hex}"[:64].ljust(16, "0")


def service_token(audience: str) -> str:
    try:
        private_key = SIGNING_KEY_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise E2EError(
            f"Cannot read {SIGNING_KEY_PATH}. Run `sh scripts/generate-local-keys.sh` "
            "before the end-to-end suites."
        ) from exc
    signer = ServiceJwtSigner(
        private_key=private_key,
        issuer=SERVICE_JWT_ISSUER,
        subject="booking-orchestrator",
        key_id=SERVICE_JWT_KEY_ID,
        ttl_seconds=60,
    )
    return signer.issue(audience)


def wait_until(
    description: str,
    predicate: Callable[[], bool],
    *,
    timeout: float,
    interval: float = POLL_INTERVAL,
) -> None:
    """Poll until the predicate holds. Never sleeps for a fixed duration."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except (httpx.HTTPError, E2EError) as exc:
            last_error = exc
        time.sleep(interval)
    suffix = f" Last error: {last_error}" if last_error else ""
    raise E2EError(f"Timed out after {timeout:.0f}s waiting for {description}.{suffix}")


def require_stack() -> None:
    """Fail with a precise message when the Compose stack is not reachable."""
    for name, url in (
        ("ESB", f"{ESB_URL}/health/ready"),
        ("Identity", f"{IDENTITY_URL}/health/ready"),
        ("Event", f"{EVENT_URL}/health/ready"),
        ("Customer", f"{CUSTOMER_URL}/health/ready"),
    ):
        try:
            response = httpx.get(url, timeout=REQUEST_TIMEOUT)
        except httpx.HTTPError as exc:
            raise E2EError(
                f"{name} is not reachable at {url}. Start the stack with "
                "`docker compose --profile all up --build --wait`."
            ) from exc
        if response.status_code != 200:
            raise E2EError(f"{name} readiness returned {response.status_code} at {url}")


@dataclass(frozen=True, slots=True)
class Browser:
    """A registered end user holding an Identity access token and Customer mapping."""

    email: str
    access_token: str
    identity_subject: str
    customer_id: str

    def headers(self, correlation: str, **extra: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-Correlation-ID": correlation,
            **extra,
        }


def register_browser_user(client: httpx.Client) -> Browser:
    """Register an Identity account and link it to a fresh Customer profile."""
    suffix = uuid.uuid4().hex[:12]
    email = f"e2e-{suffix}@example.com"
    password = f"E2e-Password-{suffix}"
    correlation = correlation_id("reg")

    registered = client.post(
        f"{IDENTITY_URL}/auth/register",
        json={"email": email, "password": password},
        headers={
            "X-Correlation-ID": correlation,
            "Idempotency-Key": f"e2e-register-{suffix}",
        },
    )
    if registered.status_code != 201:
        raise E2EError(
            f"Identity registration failed: {registered.status_code} {registered.text}"
        )
    identity_subject = str(registered.json()["userId"])

    logged_in = client.post(
        f"{IDENTITY_URL}/auth/login",
        json={"email": email, "password": password},
        headers={"X-Correlation-ID": correlation_id("login")},
    )
    if logged_in.status_code != 200:
        raise E2EError(
            f"Identity login failed: {logged_in.status_code} {logged_in.text}"
        )
    access_token = str(logged_in.json()["accessToken"])

    customer_id = _create_customer(client, email, suffix)
    _link_identity(client, customer_id, identity_subject, suffix)
    return Browser(email, access_token, identity_subject, customer_id)


def _create_customer(client: httpx.Client, email: str, suffix: str) -> str:
    created = client.post(
        f"{CUSTOMER_URL}/customers",
        json={"name": f"E2E User {suffix}", "email": email, "phone": "0901234567"},
        headers={
            "Authorization": f"Bearer {service_token('customer-service')}",
            "X-Correlation-ID": correlation_id("cus"),
            "Idempotency-Key": f"e2e-customer-{suffix}",
        },
    )
    if created.status_code not in {200, 201}:
        raise E2EError(
            f"Customer creation failed: {created.status_code} {created.text}"
        )
    return str(created.json()["customerId"])


def _link_identity(
    client: httpx.Client, customer_id: str, identity_subject: str, suffix: str
) -> None:
    linked = client.put(
        f"{CUSTOMER_URL}/internal/customers/{customer_id}/identity-link",
        json={"identitySubject": identity_subject},
        headers={
            "Authorization": f"Bearer {service_token('customer-service')}",
            "X-Correlation-ID": correlation_id("link"),
            "Idempotency-Key": f"e2e-link-{suffix}",
            "If-Match": '"1"',
        },
    )
    if linked.status_code != 200:
        raise E2EError(f"Identity link failed: {linked.status_code} {linked.text}")


@dataclass(frozen=True, slots=True)
class Inventory:
    event_id: str
    seat_ids: tuple[str, ...]


def provision_inventory(client: httpx.Client, seat_count: int = 4) -> Inventory:
    """Create an ON_SALE Event and its seat map through canonical contracts only."""
    event_id = _create_published_event(client)
    seat_ids = tuple(f"E2E-{index:03d}" for index in range(1, seat_count + 1))
    _configure_inventory(client, event_id, seat_ids)
    return Inventory(event_id, seat_ids)


def _create_published_event(client: httpx.Client) -> str:
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)

    def rfc3339(value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    suffix = uuid.uuid4().hex[:12]
    created = client.post(
        f"{EVENT_URL}/events",
        json={
            "name": f"E2E Event {suffix}",
            "venue": "E2E Arena",
            "startsAt": rfc3339(now + timedelta(days=30)),
            "saleStartsAt": rfc3339(now - timedelta(days=1)),
            "saleEndsAt": rfc3339(now + timedelta(days=29)),
            "ticketTypes": [
                {
                    "code": "VIP",
                    "name": "VIP",
                    "price": {"amountMinor": 500000, "currency": "VND"},
                }
            ],
        },
        headers={
            "Authorization": f"Bearer {service_token('event-service')}",
            "X-Correlation-ID": correlation_id("evt"),
            "Idempotency-Key": f"e2e-event-{suffix}",
        },
    )
    if created.status_code not in {200, 201}:
        raise E2EError(f"Event creation failed: {created.status_code} {created.text}")
    event = created.json()
    published = client.post(
        f"{EVENT_URL}/events/{event['eventId']}/publish",
        headers={
            "Authorization": f"Bearer {service_token('event-service')}",
            "X-Correlation-ID": correlation_id("pub"),
            "Idempotency-Key": f"e2e-publish-{suffix}",
            "If-Match": f'"{event["resourceVersion"]}"',
        },
    )
    if published.status_code != 200:
        raise E2EError(
            f"Event publish failed: {published.status_code} {published.text}"
        )
    return str(event["eventId"])


def _configure_inventory(
    client: httpx.Client, event_id: str, seat_ids: tuple[str, ...]
) -> None:
    response = client.post(
        SEAT_SOAP_URL,
        content=configure_inventory_envelope(event_id, seat_ids),
        headers={
            "Authorization": f"Bearer {service_token('seat-inventory-service')}",
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f"{SEAT_NS}/ConfigureInventory",
        },
    )
    if response.status_code != 200:
        raise E2EError(
            f"ConfigureInventory failed: {response.status_code} {response.text}"
        )


def configure_inventory_envelope(event_id: str, seat_ids: tuple[str, ...]) -> bytes:
    envelope = etree.Element(
        f"{{{SOAP_ENV_NS}}}Envelope", nsmap={"soapenv": SOAP_ENV_NS}
    )
    body = etree.SubElement(envelope, f"{{{SOAP_ENV_NS}}}Body")
    request = etree.SubElement(body, f"{{{SEAT_NS}}}ConfigureInventoryRequest")
    context = etree.SubElement(request, f"{{{SEAT_NS}}}context")
    _text(context, "correlationId", correlation_id("cfg"))
    _text(context, "idempotencyKey", f"e2e-cfg-{event_id}-v1")
    _text(context, "callerService", "e2e-tests")
    _text(context, "schemaVersion", "1")
    _text(request, "eventId", event_id)
    _text(request, "inventoryVersion", "1")
    seats = etree.SubElement(request, f"{{{SEAT_NS}}}seats")
    for index, seat_id in enumerate(seat_ids, start=1):
        seat = etree.SubElement(seats, f"{{{SEAT_NS}}}seat")
        _text(seat, "seatId", seat_id)
        _text(seat, "section", "E")
        _text(seat, "rowLabel", "1")
        _text(seat, "seatNumber", f"{index:03d}")
        _text(seat, "ticketTypeCode", "VIP")
    return etree.tostring(envelope, xml_declaration=True, encoding="UTF-8")


def _text(parent: etree._Element, name: str, value: str) -> None:
    node = etree.SubElement(parent, f"{{{SEAT_NS}}}{name}")
    node.text = value


def seat_status(client: httpx.Client, event_id: str, seat_id: str) -> str | None:
    """Read authoritative seat state directly from Seat Inventory over SOAP."""
    envelope = etree.Element(
        f"{{{SOAP_ENV_NS}}}Envelope", nsmap={"soapenv": SOAP_ENV_NS}
    )
    body = etree.SubElement(envelope, f"{{{SOAP_ENV_NS}}}Body")
    request = etree.SubElement(body, f"{{{SEAT_NS}}}CheckAvailabilityRequest")
    context = etree.SubElement(request, f"{{{SEAT_NS}}}context")
    _text(context, "correlationId", correlation_id("avail"))
    _text(context, "callerService", "e2e-tests")
    _text(context, "schemaVersion", "1")
    _text(request, "eventId", event_id)
    seats = etree.SubElement(request, f"{{{SEAT_NS}}}seatIds")
    seat = etree.SubElement(seats, f"{{{SEAT_NS}}}seat")
    _text(seat, "seatId", seat_id)
    _text(seat, "ticketTypeCode", "VIP")
    response = client.post(
        SEAT_SOAP_URL,
        content=etree.tostring(envelope, xml_declaration=True, encoding="UTF-8"),
        headers={
            "Authorization": f"Bearer {service_token('seat-inventory-service')}",
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f"{SEAT_NS}/CheckAvailability",
        },
    )
    if response.status_code != 200:
        raise E2EError(
            f"CheckAvailability failed: {response.status_code} {response.text}"
        )
    available = etree.fromstring(response.content).find(f".//{{{SEAT_NS}}}available")
    if available is None or available.text is None:
        raise E2EError("CheckAvailability response is missing available")
    return "AVAILABLE" if available.text == "true" else "TAKEN"


def place_booking(
    client: httpx.Client,
    browser: Browser,
    inventory: Inventory,
    *,
    seat_ids: tuple[str, ...],
    payment_method_token: str = "tok-e2e-success",
    idempotency_key: str | None = None,
    correlation: str | None = None,
) -> httpx.Response:
    return client.post(
        f"{ESB_URL}/api/bookings",
        json={
            "customerId": browser.customer_id,
            "eventId": inventory.event_id,
            "seatIds": list(seat_ids),
            "paymentMethodToken": payment_method_token,
        },
        headers=browser.headers(
            correlation or correlation_id("book"),
            **{"Idempotency-Key": idempotency_key or f"e2e-book-{uuid.uuid4().hex}"},
        ),
    )


def get_booking(
    client: httpx.Client, browser: Browser, booking_id: str
) -> Mapping[str, Any]:
    response = client.get(
        f"{ESB_URL}/api/bookings/{booking_id}",
        headers=browser.headers(correlation_id("read")),
    )
    if response.status_code != 200:
        raise E2EError(f"Booking read failed: {response.status_code} {response.text}")
    return dict(response.json())


def compose(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run docker compose against the repository stack for fault injection."""
    return subprocess.run(
        ["docker", "compose", *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=check,
        timeout=180,
    )


def place_booking_when_recovered(
    client: httpx.Client,
    browser: Browser,
    inventory: Inventory,
    *,
    seat_ids: tuple[str, ...],
    timeout: float = 120,
) -> httpx.Response:
    """Retry a booking until the ESB circuit closes again after an outage."""
    attempts: dict[str, httpx.Response] = {}

    def attempt() -> bool:
        response = place_booking(client, browser, inventory, seat_ids=seat_ids)
        attempts["last"] = response
        return response.status_code == 201

    wait_until(
        "the ESB circuit to close and accept a booking again",
        attempt,
        timeout=timeout,
        interval=2,
    )
    return attempts["last"]


@contextmanager
def service_stopped(service: str) -> Iterator[None]:
    """Stop one provider container for the duration of the block, then restore it."""
    compose("stop", "--timeout", "10", service)
    try:
        yield
    finally:
        compose("start", service)
        # Wait for the restarted container's own healthcheck, not the ESB's: the ESB
        # stays ready during a provider outage, so polling it would let the next
        # request run before the provider is actually serving.
        wait_until(
            f"{service} to report healthy again",
            lambda: container_health(service) == "healthy",
            timeout=READINESS_TIMEOUT,
            interval=2,
        )


@contextmanager
def service_paused(service: str) -> Iterator[None]:
    """Freeze a provider so a dispatched request is accepted but never answered.

    Unlike `service_stopped`, the socket stays open: the request leaves the ESB and is
    delivered, so the outcome is genuinely unknown rather than never dispatched. On
    resume the provider processes whatever was queued while it was frozen.
    """
    compose("pause", service)
    try:
        yield
    finally:
        compose("unpause", service, check=False)
        wait_until(
            f"{service} to report healthy again",
            lambda: container_health(service) == "healthy",
            timeout=READINESS_TIMEOUT,
            interval=2,
        )


def container_health(service: str) -> str:
    result = compose("ps", "--format", "{{.Service}}|{{.Health}}", service, check=False)
    for line in result.stdout.splitlines():
        name, _, health = line.partition("|")
        if name.strip() == service:
            return health.strip()
    return "unknown"
