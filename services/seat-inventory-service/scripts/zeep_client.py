"""Call individual SOAP operations or execute a complete local workflow."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path

import requests
from zeep import Client
from zeep.helpers import serialize_object
from zeep.transports import Transport

ROOT = Path(__file__).resolve().parents[1]


def create_client(wsdl: str, token: str) -> Client:
    session = requests.Session()
    session.headers["X-Service-Token"] = token
    return Client(wsdl=wsdl, transport=Transport(session=session, timeout=10))


def context(*, command: bool = False) -> dict[str, str]:
    suffix = uuid.uuid4().hex
    value = {
        "correlationId": f"COR-{suffix}",
        "callerService": "zeep-client",
        "schemaVersion": "1.0",
    }
    if command:
        value["idempotencyKey"] = f"IDEM-{suffix}"
    return value


def show(label: str, value: object) -> None:
    print(
        json.dumps(
            {label: serialize_object(value)},
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    )


def workflow(client: Client, event_id: str) -> None:
    seat_map = client.service.GetSeatMap(context=context(), eventId=event_id)
    show("GetSeatMap", seat_map)

    availability = client.service.CheckAvailability(
        context=context(),
        eventId=event_id,
        seatIds={"seatId": ["A-01", "A-02"]},
    )
    show("CheckAvailability", availability)

    first = client.service.ReserveSeats(
        context=context(command=True),
        bookingId=f"BKG-{uuid.uuid4().hex[:10]}",
        eventId=event_id,
        seatIds={"seatId": ["A-01"]},
        holdSeconds=120,
    )
    show("ReserveSeats", first)
    first_id = str(first.reservation.reservationId)

    queried = client.service.GetReservation(context=context(), reservationId=first_id)
    show("GetReservation", queried)

    extended = client.service.ExtendReservation(
        context=context(command=True),
        reservationId=first_id,
        expectedVersion=int(first.reservation.resourceVersion),
        extensionSeconds=30,
    )
    show("ExtendReservation", extended)

    released = client.service.ReleaseSeats(
        context=context(command=True),
        reservationId=first_id,
        reasonCode="CLIENT_DEMO",
    )
    show("ReleaseSeats", released)

    second = client.service.ReserveSeats(
        context=context(command=True),
        bookingId=f"BKG-{uuid.uuid4().hex[:10]}",
        eventId=event_id,
        seatIds={"seatId": ["A-02"]},
        holdSeconds=120,
    )
    second_id = str(second.reservation.reservationId)
    confirmed = client.service.ConfirmSeats(
        context=context(command=True),
        reservationId=second_id,
        expectedVersion=int(second.reservation.resourceVersion),
    )
    show("ConfirmSeats", confirmed)

    expired = client.service.ExpireReservations(context=context(), batchSize=100)
    show("ExpireReservations", expired)


def single_operation(
    client: Client,
    operation: str,
    *,
    event_id: str,
    reservation_id: str | None,
) -> None:
    if operation == "GetSeatMap":
        show(operation, client.service.GetSeatMap(context=context(), eventId=event_id))
    elif operation == "CheckAvailability":
        show(
            operation,
            client.service.CheckAvailability(
                context=context(),
                eventId=event_id,
                seatIds={"seatId": ["A-01"]},
            ),
        )
    elif operation == "ReserveSeats":
        show(
            operation,
            client.service.ReserveSeats(
                context=context(command=True),
                bookingId=f"BKG-{uuid.uuid4().hex[:10]}",
                eventId=event_id,
                seatIds={"seatId": ["A-01"]},
                holdSeconds=120,
            ),
        )
    elif operation == "ExpireReservations":
        show(
            operation,
            client.service.ExpireReservations(context=context(), batchSize=100),
        )
    else:
        if not reservation_id:
            raise SystemExit(f"--reservation-id is required for {operation}")
        if operation == "GetReservation":
            result = client.service.GetReservation(
                context=context(), reservationId=reservation_id
            )
        elif operation == "ExtendReservation":
            result = client.service.ExtendReservation(
                context=context(command=True),
                reservationId=reservation_id,
                expectedVersion=1,
                extensionSeconds=30,
            )
        elif operation == "ConfirmSeats":
            result = client.service.ConfirmSeats(
                context=context(command=True),
                reservationId=reservation_id,
                expectedVersion=1,
            )
        elif operation == "ReleaseSeats":
            result = client.service.ReleaseSeats(
                context=context(command=True),
                reservationId=reservation_id,
                reasonCode="CLIENT_REQUEST",
            )
        else:
            raise SystemExit(f"Unsupported operation: {operation}")
        show(operation, result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "operation",
        choices=[
            "workflow",
            "GetSeatMap",
            "CheckAvailability",
            "ReserveSeats",
            "GetReservation",
            "ExtendReservation",
            "ConfirmSeats",
            "ReleaseSeats",
            "ExpireReservations",
        ],
    )
    parser.add_argument("--wsdl", default=os.getenv("SEAT_WSDL_URL"))
    parser.add_argument("--token", default=os.getenv("SEAT_SERVICE_TOKEN"))
    parser.add_argument("--event-id", default="EVT-DEMO")
    parser.add_argument("--reservation-id")
    args = parser.parse_args()
    if not args.wsdl:
        parser.error("--wsdl or SEAT_WSDL_URL is required")
    if not args.token:
        parser.error("--token or SEAT_SERVICE_TOKEN is required")

    client = create_client(args.wsdl, args.token)
    if args.operation == "workflow":
        workflow(client, args.event_id)
    else:
        single_operation(
            client,
            args.operation,
            event_id=args.event_id,
            reservation_id=args.reservation_id,
        )


if __name__ == "__main__":
    main()
