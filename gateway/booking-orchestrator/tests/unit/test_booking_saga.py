import time,pytest
from types import SimpleNamespace
from app.application.booking import BookingSaga
from app.domain.models import RequestContext,Principal
from app.persistence.repositories import InMemoryRepository
from tests.fakes import Customer,Event,Seat,Booking,Payment,Ticket
@pytest.mark.asyncio
async def test_confirm_seats_before_issue_tickets_and_mixed_prices():
 log=[];repo=InMemoryRepository();s=BookingSaga(Customer(),Event(),Seat(log),Booking(log),Payment(log),Ticket(log),repo,repo,SimpleNamespace(reservation_ttl_seconds=321))
 ctx=RequestContext('c','1'*32,time.monotonic()+5,Principal('u',frozenset({'CUSTOMER'}),'cust-1'))
 status,body=await s.place({'eventId':'e1','seatIds':['A1','V1'],'paymentMethodToken':'success'},'k1',ctx)
 assert status==201 and body['status']=='CONFIRMED'
 assert log.index('confirm-seat')<log.index('issue-ticket')
 wf=next(iter(repo.workflows.values()));assert wf.amount_minor==300
@pytest.mark.asyncio
async def test_unknown_payment_returns_202_without_ticket():
 log=[];repo=InMemoryRepository();s=BookingSaga(Customer(),Event(),Seat(log),Booking(log),Payment(log,'UNKNOWN'),Ticket(log),repo,repo,SimpleNamespace(reservation_ttl_seconds=111))
 ctx=RequestContext('c','1'*32,time.monotonic()+5,Principal('u',frozenset(),'cust-1'))
 status,body=await s.place({'eventId':'e1','seatIds':['A1'],'paymentMethodToken':'timeout'},'k2',ctx)
 assert status==202 and body['paymentStatus']=='UNKNOWN' and 'issue-ticket' not in log

class ListTicket(Ticket):
    async def issue(self, *args):
        if args:
            self.payloads["issue"] = args[0]
        self.log.append("issue-ticket")
        # Canonical Ticket Service contract returns a plain array for POST /tickets:issue.
        return [{"ticketId": "t1"}, {"ticketId": "t2"}]


@pytest.mark.asyncio
async def test_ticket_issue_plain_array_matches_provider_contract():
    log = []
    repo = InMemoryRepository()
    saga = BookingSaga(
        Customer(),
        Event(),
        Seat(log),
        Booking(log),
        Payment(log),
        ListTicket(log),
        repo,
        repo,
        SimpleNamespace(reservation_ttl_seconds=321),
    )
    ctx = RequestContext(
        "corr-ticket-array",
        "1" * 32,
        time.monotonic() + 5,
        Principal("u", frozenset({"CUSTOMER"}), "cust-1"),
    )
    status, body = await saga.place(
        {"eventId": "e1", "seatIds": ["A1", "V1"], "paymentMethodToken": "success"},
        "ticket-array-key",
        ctx,
    )
    assert status == 201
    assert body["ticketIds"] == ["t1", "t2"]


def test_internal_workflow_states_are_not_exposed_as_booking_service_states():
    from app.domain.models import PaymentStatus, Workflow, WorkflowStatus

    workflow = Workflow(
        workflow_id="wf-1",
        idempotency_key="idem-12345678",
        request_hash="hash",
        customer_id="cust-1",
        event_id="event-1",
        seat_ids=["A1"],
        booking_id="booking-1",
        booking_version=4,
        amount_minor=100,
        currency="VND",
        evidence={"correlationId": "corr-1"},
    )
    workflow.status = WorkflowStatus.PAYMENT_UNKNOWN
    workflow.payment_status = PaymentStatus.UNKNOWN
    body = BookingSaga._response(workflow)
    assert body["status"] == "PAYMENT_PROCESSING"
    assert body["paymentStatus"] == "UNKNOWN"
    assert body["status"] != WorkflowStatus.PAYMENT_UNKNOWN.value
