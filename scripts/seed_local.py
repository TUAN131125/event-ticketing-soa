"""Provision the local demo Event and its seat map through canonical contracts only.

The job is a one-shot local/demo bootstrap. It never writes to a service database, never
runs inside a migration and never runs at application startup. It is idempotent: rerunning
it leaves the same Event and the same seat map.
"""

from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from lxml import etree

# Importable from the repository checkout and from the container image, where the
# script is mounted next to the packaged libs/ directory.
for candidate in (Path(__file__).resolve().parents[1], Path(__file__).resolve().parent):
    if (candidate / "libs" / "platform_security").is_dir():
        sys.path.insert(0, str(candidate))
        break

from libs.platform_security import ServiceJwtSigner  # noqa: E402

SEAT_NS = "urn:event-ticketing:seat:v1"
SOAP_ENV_NS = "http://schemas.xmlsoap.org/soap/envelope/"
DEMO_EVENT_ID = "EV001"
DEMO_EVENT_NAME = "Dem nhac mua he"
SECTIONS = ("A", "B")
ROWS_PER_SECTION = 2
SEATS_PER_ROW = 5
TICKET_TYPE_BY_SECTION = {"A": "VIP", "B": "STANDARD"}


class SeedError(RuntimeError):
    """Raised when local provisioning cannot complete through a canonical contract."""


@dataclass(frozen=True, slots=True)
class SeedConfig:
    event_base_url: str
    seat_soap_url: str
    signer: ServiceJwtSigner
    event_audience: str
    seat_audience: str
    timeout_seconds: float

    @classmethod
    def from_environment(cls) -> SeedConfig:
        if os.getenv("SEED_LOCAL_ENABLED", "").strip().lower() not in {
            "1",
            "true",
            "yes",
        }:
            raise SeedError(
                "SEED_LOCAL_ENABLED must be true; local seeding is opt-in and must "
                "never run against a shared or production environment"
            )
        private_key_path = os.getenv("SEED_SERVICE_JWT_PRIVATE_KEY_PATH", "").strip()
        if not private_key_path:
            raise SeedError("SEED_SERVICE_JWT_PRIVATE_KEY_PATH is required")
        try:
            private_key = Path(private_key_path).read_text(encoding="utf-8")
        except OSError as exc:
            raise SeedError(f"Cannot read signing key {private_key_path}") from exc
        return cls(
            event_base_url=_required("SEED_EVENT_BASE_URL").rstrip("/"),
            seat_soap_url=_required("SEED_SEAT_SOAP_URL"),
            signer=ServiceJwtSigner(
                private_key=private_key,
                issuer=_required("SEED_SERVICE_JWT_ISSUER"),
                subject=os.getenv("SEED_SERVICE_JWT_SUBJECT", "booking-orchestrator"),
                key_id=_required("SEED_SERVICE_JWT_KEY_ID"),
                ttl_seconds=60,
            ),
            event_audience=os.getenv("SEED_EVENT_AUDIENCE", "event-service"),
            seat_audience=os.getenv("SEED_SEAT_AUDIENCE", "seat-inventory-service"),
            timeout_seconds=float(os.getenv("SEED_TIMEOUT_SECONDS", "10")),
        )


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SeedError(f"{name} is required")
    return value


def seat_layout() -> tuple[dict[str, str], ...]:
    seats: list[dict[str, str]] = []
    for section in SECTIONS:
        for row in range(1, ROWS_PER_SECTION + 1):
            for number in range(1, SEATS_PER_ROW + 1):
                seats.append(
                    {
                        "seatId": f"{section}{row}-{number:02d}",
                        "section": section,
                        "rowLabel": str(row),
                        "seatNumber": f"{number:02d}",
                        "ticketTypeCode": TICKET_TYPE_BY_SECTION[section],
                    }
                )
    return tuple(seats)


def ensure_event(client: httpx.Client, config: SeedConfig, correlation_id: str) -> str:
    """Resolve or create the demo Event and leave it ON_SALE, using only Event APIs."""
    event = _find_event(client, config, correlation_id)
    if event is None:
        event = _create_event(client, config, correlation_id)
    if event["status"] == "DRAFT":
        event = _publish_event(client, config, correlation_id, event)
    if event["status"] != "ON_SALE":
        raise SeedError(
            f"Demo event {event['eventId']} is {event['status']}; local seeding "
            "requires an ON_SALE event and never forces an invalid transition"
        )
    return str(event["eventId"])


def _event_headers(config: SeedConfig, correlation_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.signer.issue(config.event_audience)}",
        "X-Correlation-ID": correlation_id,
    }


def _find_event(
    client: httpx.Client, config: SeedConfig, correlation_id: str
) -> dict[str, Any] | None:
    direct = client.get(
        f"{config.event_base_url}/events/{DEMO_EVENT_ID}",
        headers=_event_headers(config, correlation_id),
    )
    if direct.status_code == 200:
        return dict(direct.json())
    if direct.status_code != 404:
        raise SeedError(f"Event lookup failed with {direct.status_code}: {direct.text}")

    # A previous run may have created the demo event under a generated identifier.
    listed = client.get(
        f"{config.event_base_url}/events",
        headers=_event_headers(config, correlation_id),
    )
    if listed.status_code != 200:
        raise SeedError(
            f"Event listing failed with {listed.status_code}: {listed.text}"
        )
    for item in listed.json():
        if item.get("name") == DEMO_EVENT_NAME:
            return dict(item)
    return None


def _create_event(
    client: httpx.Client, config: SeedConfig, correlation_id: str
) -> dict[str, Any]:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "name": DEMO_EVENT_NAME,
        "venue": "Nha hat Thanh pho",
        "startsAt": _rfc3339(now + timedelta(days=30)),
        "saleStartsAt": _rfc3339(now - timedelta(days=1)),
        "saleEndsAt": _rfc3339(now + timedelta(days=29)),
        "ticketTypes": [
            {
                "code": "VIP",
                "name": "VIP",
                "price": {"amountMinor": 500000, "currency": "VND"},
            },
            {
                "code": "STANDARD",
                "name": "Standard",
                "price": {"amountMinor": 250000, "currency": "VND"},
            },
        ],
    }
    created = client.post(
        f"{config.event_base_url}/events",
        json=payload,
        headers={
            **_event_headers(config, correlation_id),
            "Idempotency-Key": f"seed-local-{DEMO_EVENT_ID}",
        },
    )
    if created.status_code not in {200, 201}:
        raise SeedError(
            f"Event creation failed with {created.status_code}: {created.text}"
        )
    return dict(created.json())


def _publish_event(
    client: httpx.Client,
    config: SeedConfig,
    correlation_id: str,
    event: dict[str, Any],
) -> dict[str, Any]:
    published = client.post(
        f"{config.event_base_url}/events/{event['eventId']}/publish",
        headers={
            **_event_headers(config, correlation_id),
            "Idempotency-Key": f"seed-local-publish-{event['eventId']}",
            "If-Match": f'"{event["resourceVersion"]}"',
        },
    )
    if published.status_code != 200:
        raise SeedError(
            f"Event publish failed with {published.status_code}: {published.text}"
        )
    return dict(published.json())


def _rfc3339(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def configure_inventory_envelope(
    event_id: str, correlation_id: str, inventory_version: int
) -> bytes:
    envelope = etree.Element(
        f"{{{SOAP_ENV_NS}}}Envelope", nsmap={"soapenv": SOAP_ENV_NS}
    )
    body = etree.SubElement(envelope, f"{{{SOAP_ENV_NS}}}Body")
    request = etree.SubElement(body, f"{{{SEAT_NS}}}ConfigureInventoryRequest")
    context = etree.SubElement(request, f"{{{SEAT_NS}}}context")
    _text(context, "correlationId", correlation_id)
    _text(context, "idempotencyKey", f"seed-local-{event_id}-v{inventory_version}")
    _text(context, "callerService", "seed-local")
    _text(context, "schemaVersion", "1")
    _text(request, "eventId", event_id)
    _text(request, "inventoryVersion", str(inventory_version))
    seats = etree.SubElement(request, f"{{{SEAT_NS}}}seats")
    for definition in seat_layout():
        seat = etree.SubElement(seats, f"{{{SEAT_NS}}}seat")
        for name, value in definition.items():
            _text(seat, name, value)
    return etree.tostring(envelope, xml_declaration=True, encoding="UTF-8")


def _text(parent: etree._Element, name: str, value: str) -> None:
    node = etree.SubElement(parent, f"{{{SEAT_NS}}}{name}")
    node.text = value


def configure_inventory(
    client: httpx.Client, config: SeedConfig, event_id: str, correlation_id: str
) -> str:
    response = client.post(
        config.seat_soap_url,
        content=configure_inventory_envelope(event_id, correlation_id, 1),
        headers={
            "Authorization": f"Bearer {config.signer.issue(config.seat_audience)}",
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f"{SEAT_NS}/ConfigureInventory",
        },
    )
    if response.status_code != 200:
        if "INVENTORY_CONFLICT" in response.text:
            # A previous run already provisioned inventory version 1 for this event.
            return "ALREADY_CONFIGURED"
        raise SeedError(
            f"ConfigureInventory failed with {response.status_code}: {response.text}"
        )
    document = etree.fromstring(response.content)
    status = document.find(f".//{{{SEAT_NS}}}status")
    if status is None or status.text is None:
        raise SeedError("ConfigureInventory response is missing status")
    return status.text


def main() -> int:
    try:
        config = SeedConfig.from_environment()
    except SeedError as exc:
        print(f"SEED_LOCAL FAIL {exc}", file=sys.stderr)
        return 2

    correlation_id = f"seed-local-{uuid.uuid4().hex[:16]}"
    try:
        with httpx.Client(timeout=config.timeout_seconds) as client:
            event_id = ensure_event(client, config, correlation_id)
            status = configure_inventory(client, config, event_id, correlation_id)
    except (SeedError, httpx.HTTPError, etree.XMLSyntaxError) as exc:
        print(f"SEED_LOCAL FAIL {exc}", file=sys.stderr)
        return 1

    print(
        f"SEED_LOCAL OK eventId={event_id} seats={len(seat_layout())} "
        f"inventory={status} correlationId={correlation_id}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
