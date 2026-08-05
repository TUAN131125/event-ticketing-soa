from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from app.adapters.soap.seat import NS, SeatSoapAdapter
from app.domain.errors import BusinessFault, IdempotencyConflict
from app.domain.models import (
    OperationResult,
    OutboxItem,
    WorkflowEvidence,
    WorkflowPhase,
)
from app.persistence.database import Database
from app.persistence.memory import InMemoryRepositories
from app.persistence.repositories import SqlRepositories
from app.resilience.policies import (
    Bulkhead,
    CircuitBreaker,
    ResilienceExecutor,
    RetryClass,
)
from app.security.jwt import JwtSigner
from app.workers.outbox import OutboxDispatcher
from app.workers.reconciliation import ReconciliationWorker, RecoveryScanner
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fakes import FakeClock, FakeProviders, request_context

SEAT_XSD = Path(__file__).resolve().parents[3] / "contracts" / "seat-inventory.xsd"
GATEWAY_ROOT = Path(__file__).resolve().parents[3] / "gateway" / "booking-orchestrator"


def executor() -> ResilienceExecutor:
    return ResilienceExecutor(
        {RetryClass.SAFE_READ: 1, RetryClass.IDEMPOTENT_COMMAND: 1},
        0,
        CircuitBreaker(5, 1),
        Bulkhead(2),
    )


def service_signer() -> JwtSigner:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return JwtSigner(
        private, "booking-orchestrator", "booking-orchestrator", "internal-1"
    )


@pytest.mark.asyncio
async def test_seat_soap_adapter_translates_to_provider_contract_and_flattens_reservation() -> (
    None
):
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["action"] = request.headers["SOAPAction"]
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = request.content.decode()
        response = f'''<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tns="{NS}"><soap:Body><tns:ReserveSeatsResponse><tns:reservationId>RES-1</tns:reservationId><tns:bookingId>BK-1</tns:bookingId><tns:eventId>EVT-1</tns:eventId><tns:status>ACTIVE</tns:status><tns:expiresAt>2026-08-03T03:10:00Z</tns:expiresAt><tns:resourceVersion>1</tns:resourceVersion></tns:ReserveSeatsResponse></soap:Body></soap:Envelope>'''
        return httpx.Response(200, content=response.encode())

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = SeatSoapAdapter(
        "https://seat.test/soap",
        client,
        executor(),
        str(SEAT_XSD),
        service_signer(),
    )
    payload = {
        "bookingId": "BK-1",
        "eventId": "EVT-1",
        "seatIds": [{"seatId": "SEAT-1", "ticketTypeCode": "STANDARD"}],
        "ttlSeconds": 600,
    }
    result = await adapter.reserve_seats(
        payload, "stable-reserve-key", request_context()
    )
    assert result["reservationId"] == "RES-1"
    assert result["resourceVersion"] == 1
    assert result["status"] == "ACTIVE"
    assert captured["action"] == "urn:event-ticketing:seat:v1/ReserveSeats"
    assert str(captured["authorization"]).startswith("Bearer ")
    body = str(captured["body"])
    for expected in (
        "BK-1",
        "EVT-1",
        "SEAT-1",
        "600",
        "stable-reserve-key",
        "booking-orchestrator",
    ):
        assert expected in body
    assert "ttlSeconds" in body
    assert "ticketTypeCode" in body
    await client.aclose()


@pytest.mark.asyncio
async def test_seat_soap_fault_is_normalized_without_raw_xml() -> None:
    fault = f'''<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tns="{NS}"><soap:Body><soap:Fault><faultcode>soap:Client</faultcode><faultstring>Unavailable</faultstring><detail><tns:SeatServiceFault><tns:code>SEAT_UNAVAILABLE</tns:code><tns:message>Seat unavailable.</tns:message><tns:correlationId>CORRELATION-0001</tns:correlationId><tns:retryable>false</tns:retryable></tns:SeatServiceFault></detail></soap:Fault></soap:Body></soap:Envelope>'''
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(409, content=fault.encode())
        )
    )
    adapter = SeatSoapAdapter(
        "https://seat.test/soap",
        client,
        executor(),
        str(SEAT_XSD),
        service_signer(),
    )
    with pytest.raises(BusinessFault) as raised:
        await adapter.check_availability("EVT-1", ["SEAT-1"], request_context())
    assert raised.value.code == "SEAT_UNAVAILABLE"
    assert raised.value.details == {"soapFaultCode": "SEAT_UNAVAILABLE"}
    assert "Envelope" not in str(raised.value.details)
    await client.aclose()


@pytest.mark.asyncio
async def test_sql_repositories_persist_workflow_idempotency_trace_outbox_and_jobs(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'esb.db'}"
    migration = Config(str(GATEWAY_ROOT / "alembic.ini"))
    migration.set_main_option("script_location", str(GATEWAY_ROOT / "alembic"))
    migration.set_main_option("sqlalchemy.url", database_url)
    await asyncio.to_thread(command.upgrade, migration, "head")
    database = Database(database_url)
    repositories = SqlRepositories(database)
    claim = await repositories.claim("placeBooking", "subject", "stable-key", "hash-a")
    workflow = WorkflowEvidence(
        claim.workflow_id,
        "placeBooking",
        "subject",
        "hash-a",
        "CORRELATION-0001",
        WorkflowPhase.CONFIRMED,
        booking_id="BK-1",
    )
    await repositories.create(workflow)
    await repositories.complete(
        "placeBooking",
        "subject",
        "stable-key",
        OperationResult(201, {"bookingId": "BK-1"}),
    )
    replay = await repositories.claim("placeBooking", "subject", "stable-key", "hash-a")
    assert replay.kind == "REPLAY"
    with pytest.raises(IdempotencyConflict):
        await repositories.claim("placeBooking", "subject", "stable-key", "hash-b")
    await repositories.append(
        "CORRELATION-0001", "booking-service", "createBooking", "SUCCESS", 12
    )
    await repositories.enqueue_many(
        claim.workflow_id,
        [
            OutboxItem(
                "MSG-1",
                "realtime",
                "booking.status",
                {"bookingId": "BK-1"},
                "CORRELATION-0001",
            )
        ],
    )
    await repositories.schedule(
        claim.workflow_id, "PAYMENT_UNKNOWN", {"paymentId": "PAY-1"}, "reconcile-key"
    )
    assert (await repositories.get(claim.workflow_id)).booking_id == "BK-1"  # type: ignore[union-attr]
    assert len(await repositories.list("CORRELATION-0001")) == 1
    assert len(await repositories.due_outbox(FakeClock().now(), 10)) == 1
    assert len(await repositories.due_jobs(FakeClock().now(), 10)) == 1
    await database.dispose()


@pytest.mark.asyncio
async def test_outbox_failure_is_retried_without_changing_booking_workflow() -> None:
    repositories = InMemoryRepositories()
    providers = FakeProviders()

    class FailingSideEffect:
        async def publish(self, payload, message_id, context):
            raise RuntimeError("offline")

    workflow = WorkflowEvidence(
        "WF-1",
        "placeBooking",
        "subject",
        "hash",
        "CORRELATION-0001",
        WorkflowPhase.CONFIRMED,
        booking_id="BK-1",
    )
    await repositories.create(workflow)
    await repositories.enqueue_many(
        "WF-1",
        [
            OutboxItem(
                "MSG-1",
                "notification",
                "booking.confirmed",
                {"bookingId": "BK-1"},
                "CORRELATION-0001",
            )
        ],
    )
    dispatcher = OutboxDispatcher(
        repositories, FailingSideEffect(), providers, FakeClock()
    )
    assert await dispatcher.run_once() == 1
    assert repositories.outbox["MSG-1"]["attempts"] == 1
    assert repositories.workflows["WF-1"].phase == WorkflowPhase.CONFIRMED


@pytest.mark.asyncio
async def test_recovery_scanner_recreates_payment_unknown_reconciliation() -> None:
    repositories = InMemoryRepositories()
    workflow = WorkflowEvidence(
        "WF-1",
        "placeBooking",
        "subject",
        "hash",
        "CORRELATION-0001",
        WorkflowPhase.PAYMENT_PROCESSING,
        booking_id="BK-1",
        payment_id="PAY-1",
    )
    from app.domain.models import PaymentOutcome

    workflow.payment_status = PaymentOutcome.UNKNOWN
    await repositories.create(workflow)
    assert await RecoveryScanner(repositories, repositories).recover() == 1
    assert {job["kind"] for job in repositories.jobs.values()} == {"PAYMENT_UNKNOWN"}


@pytest.mark.asyncio
async def test_process_restart_resumes_captured_payment_through_confirmation_and_outbox() -> (
    None
):
    from app.domain.models import Money, PaymentOutcome

    repositories = InMemoryRepositories()
    providers = FakeProviders()
    providers.payment_outcomes["reconcilePayment"] = {"status": "CAPTURED"}
    workflow = WorkflowEvidence(
        "WF-1",
        "placeBooking",
        "subject",
        "hash",
        "CORRELATION-0001",
        WorkflowPhase.PAYMENT_PROCESSING,
        booking_id="BK-1",
        customer_id="CUS-1",
        reservation_id="RES-1",
        reservation_version=1,
        payment_id="PAY-1",
        payment_status=PaymentOutcome.UNKNOWN,
        total=Money(100000, "VND"),
        evidence={
            "eventId": "EVT-1",
            "seatIds": ["SEAT-1"],
            "ticketTypeCode": "STANDARD",
        },
    )
    await repositories.create(workflow)
    await repositories.schedule(
        "WF-1",
        "PAYMENT_UNKNOWN",
        {"paymentId": "PAY-1", "bookingId": "BK-1"},
        "reconcile-key",
    )
    worker = ReconciliationWorker(
        repositories,
        repositories,
        providers,
        providers,
        providers,
        providers,
        repositories,
        FakeClock(),
    )
    assert await worker.run_once() == 1
    assert repositories.workflows["WF-1"].phase == WorkflowPhase.CONFIRMED
    assert not repositories.jobs
    assert len(repositories.outbox) == 2
    names = [name for name, _ in providers.calls]
    assert (
        names.index("reconcilePayment")
        < names.index("issueTickets")
        < names.index("ConfirmSeats")
        < names.index("bookingConfirm")
    )
