"""Payment outcome classification: PAID, DECLINED, NOT_DISPATCHED and UNKNOWN."""

from __future__ import annotations

import httpx
import pytest
from app.adapters.rest.base import RestClient
from app.domain.errors import (
    AmbiguousOutcome,
    BusinessFault,
    CommandNotDispatched,
    DependencyFailure,
)
from app.domain.models import PaymentOutcome, WorkflowPhase
from app.resilience.policies import (
    Bulkhead,
    CircuitBreaker,
    ResilienceExecutor,
    RetryClass,
)
from fakes import FakeProviders, request_context
from test_booking_saga import build_booking, call_names


def declined_fault() -> BusinessFault:
    return BusinessFault("PAYMENT_DECLINED", "Payment was declined.", 402, False)


@pytest.mark.asyncio
async def test_captured_payment_confirms_the_booking() -> None:
    saga, providers, repositories, command = build_booking(FakeProviders())
    result = await saga.execute(command, request_context())
    names = call_names(providers)
    assert result.status_code == 201
    assert result.body["status"] == "CONFIRMED"
    assert names.index("ConfirmSeats") < len(names)
    assert "issueTickets" in names
    assert next(iter(repositories.workflows.values())).phase is WorkflowPhase.CONFIRMED


@pytest.mark.asyncio
async def test_business_402_is_declined_and_compensates() -> None:
    providers = FakeProviders()
    providers.payment_outcomes["authorizePayment"] = declined_fault()
    saga, providers, repositories, command = build_booking(providers)
    result = await saga.execute(command, request_context())
    names = call_names(providers)
    assert result.status_code == 402
    assert "ReleaseSeats" in names
    assert "issueTickets" not in names
    assert not repositories.jobs, (
        "a decline is authoritative and needs no reconciliation"
    )


@pytest.mark.asyncio
async def test_circuit_open_before_dispatch_releases_without_reconciliation() -> None:
    providers = FakeProviders()
    providers.payment_outcomes["authorizePayment"] = CommandNotDispatched(
        "/payments/PAY-1/authorize", "CIRCUIT_OPEN"
    )
    saga, providers, repositories, command = build_booking(providers)
    result = await saga.execute(command, request_context())
    names = call_names(providers)
    assert result.status_code == 503
    assert result.body["error"]["code"] == "PAYMENT_NOT_DISPATCHED"
    assert names.index("ReleaseSeats") < names.index("bookingFail")
    assert "issueTickets" not in names
    assert not repositories.jobs, "nothing was sent, so there is nothing to reconcile"
    workflow = next(iter(repositories.workflows.values()))
    assert workflow.payment_status is PaymentOutcome.NOT_DISPATCHED
    assert workflow.evidence["paymentDispatch"] == {
        "operation": "authorizePayment",
        "dispatched": False,
    }


@pytest.mark.asyncio
async def test_create_payment_not_dispatched_never_creates_a_payment() -> None:
    providers = FakeProviders()
    providers.create_payment_outcome = CommandNotDispatched("/payments", "CIRCUIT_OPEN")
    saga, providers, repositories, command = build_booking(providers)
    result = await saga.execute(command, request_context())
    names = call_names(providers)
    assert result.status_code == 503
    assert result.body["error"]["code"] == "PAYMENT_NOT_DISPATCHED"
    assert "ReleaseSeats" in names
    assert "authorizePayment" not in names
    assert not repositories.jobs


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        AmbiguousOutcome("/payments/PAY-1/authorize"),
        DependencyFailure(
            "DEPENDENCY_UNAVAILABLE", "Dependency is unavailable.", 503, True
        ),
    ],
    ids=["timeout-after-dispatch", "ambiguous-5xx"],
)
async def test_a_dispatched_command_with_no_answer_becomes_unknown(
    failure: Exception,
) -> None:
    providers = FakeProviders()
    providers.payment_outcomes["authorizePayment"] = failure
    saga, providers, repositories, command = build_booking(providers)
    result = await saga.execute(command, request_context())
    names = call_names(providers)
    assert result.status_code == 202
    assert "ReleaseSeats" not in names, "an unknown outcome must never release the seat"
    assert "issueTickets" not in names
    workflow = next(iter(repositories.workflows.values()))
    assert workflow.payment_status is PaymentOutcome.UNKNOWN
    job = next(iter(repositories.jobs.values()))
    assert job["kind"] == "PAYMENT_UNKNOWN"
    assert job["deadlineAt"] is not None, "reconciliation must be bounded by a deadline"


@pytest.mark.asyncio
async def test_ambiguous_create_payment_reconciles_with_the_original_key() -> None:
    providers = FakeProviders()
    providers.create_payment_outcome = AmbiguousOutcome("/payments")
    saga, providers, repositories, command = build_booking(providers)
    result = await saga.execute(command, request_context())
    assert result.status_code == 202
    job = next(iter(repositories.jobs.values()))
    assert job["payload"]["createIdempotencyKey"], (
        "the worker must replay createPayment with the original key, never a new one"
    )
    assert "ReleaseSeats" not in call_names(providers)


@pytest.mark.asyncio
async def test_rest_client_marks_pre_dispatch_rejection_but_not_transport_failure() -> (
    None
):
    """CommandNotDispatched must mean 'no byte left', never 'answer lost'."""

    def executor(circuit: CircuitBreaker) -> ResilienceExecutor:
        return ResilienceExecutor({RetryClass.NONE: 1}, 0.0, circuit, Bulkhead(4))

    def connect_failure(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    def answer_lost(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("no answer", request=request)

    healthy = CircuitBreaker(threshold=5, recovery_seconds=60)

    # An open circuit rejects the command before the adapter is even invoked.
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer_lost)) as http:
        open_circuit = CircuitBreaker(threshold=1, recovery_seconds=60)
        open_circuit.failure()
        blocked = RestClient(
            "https://payment",
            "payment-service",
            http,
            _signer(),
            executor(open_circuit),
        )
        with pytest.raises(CommandNotDispatched):
            await blocked.request("POST", "/payments", request_context())

        # A read timeout means the request was written; the outcome is unknown.
        dispatching = RestClient(
            "https://payment", "payment-service", http, _signer(), executor(healthy)
        )
        with pytest.raises(DependencyFailure) as lost:
            await dispatching.request("POST", "/payments", request_context())
    assert not isinstance(lost.value, CommandNotDispatched)

    # A refused connection means nothing was written at all.
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(connect_failure)
    ) as http:
        refused = RestClient(
            "https://payment",
            "payment-service",
            http,
            _signer(),
            executor(CircuitBreaker(threshold=5, recovery_seconds=60)),
        )
        with pytest.raises(CommandNotDispatched):
            await refused.request("POST", "/payments", request_context())


def _signer() -> object:
    class Signer:
        def service_token(self, audience: str) -> str:
            return "token"

    return Signer()
