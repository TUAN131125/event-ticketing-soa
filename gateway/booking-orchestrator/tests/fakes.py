from __future__ import annotations

from app.domain.models import Principal


class Auth:
    async def verify(self, authorization: str) -> Principal:
        return Principal(
            "user-1",
            frozenset({"CUSTOMER", "ADMIN", "CHECKIN_STAFF"}),
            "cust-1",
        )


class Customer:
    async def resolve_identity(self, subject: str, ctx):
        return {"customerId": "cust-1"}


class Event:
    def __init__(self):
        self.calls = []

    async def list_events(self, params, ctx):
        return []

    async def get_event(self, event_id: str, ctx):
        return {
            "eventId": event_id,
            "ticketTypes": [
                {"code": "VIP", "price": {"amountMinor": 200, "currency": "VND"}},
                {"code": "STD", "price": {"amountMinor": 100, "currency": "VND"}},
            ],
        }

    async def check_sale_eligibility(self, event_id: str, ctx):
        return {"eligible": True}

    async def admin_command(self, *args):
        self.calls.append(args)
        return {"ok": True}


class Seat:
    def __init__(self, log):
        self.log = log
        self.last_ttl = None
        self.last_seat_references = None

    async def get_seat_map(self, event_id: str, ctx):
        return {
            "seats": [
                {"seatId": "A1", "ticketTypeCode": "STD", "status": "AVAILABLE"},
                {"seatId": "V1", "ticketTypeCode": "VIP", "status": "AVAILABLE"},
            ]
        }

    async def check_availability(self, event_id: str, seat_references, ctx):
        self.last_seat_references = seat_references
        return {"available": True}

    async def reserve(
        self,
        booking_id: str,
        event_id: str,
        seat_references,
        ttl_seconds: int,
        idempotency_key: str,
        ctx,
    ):
        self.last_ttl = ttl_seconds
        self.last_seat_references = seat_references
        self.log.append("reserve")
        return {
            "reservationId": "r1",
            "resourceVersion": 1,
            "status": "RESERVED",
        }

    async def confirm(
        self,
        reservation_id: str,
        expected_version: int,
        idempotency_key: str,
        ctx,
    ):
        self.log.append("confirm-seat")
        return {"resourceVersion": 2, "status": "CONFIRMED"}

    async def release(
        self,
        reservation_id: str,
        reason_code: str,
        idempotency_key: str,
        ctx,
    ):
        self.log.append("release-seat")
        return {"status": "RELEASED"}


class Booking:
    def __init__(self, log):
        self.log = log
        self.v = 0
        self.last_create = None
        self.current_status = "PENDING"
        self.payloads: dict[str, dict] = {}

    def r(self, status: str = "PENDING"):
        self.v += 1
        self.current_status = status
        return {
            "bookingId": "b1",
            "customerId": "cust-1",
            "resourceVersion": self.v,
            "status": status,
            "reservationId": "r1",
            "reservationVersion": 2,
            "paymentId": "p1",
            "paymentStatus": "CAPTURED",
            "total": {"amountMinor": 300, "currency": "VND"},
            "ticketIds": ["t1"],
        }

    async def create(self, payload, key, ctx):
        self.last_create = payload
        self.payloads["create"] = payload
        self.log.append("booking-create")
        return self.r()

    async def get(self, *args):
        return self.r(self.current_status)

    async def list_customer(self, *args):
        return []

    async def attach_reservation(self, *args):
        if len(args) > 1:
            self.payloads["reservation"] = args[1]
        self.log.append("booking-reserve")
        return self.r("SEAT_RESERVED")

    async def confirm_reservation(self, *args):
        if len(args) > 1:
            self.payloads["reservation-confirmed"] = args[1]
        self.log.append("booking-seat-confirm")
        return self.r("SEAT_RESERVED")

    async def start_payment(self, *args):
        if len(args) > 1:
            self.payloads["payment-started"] = args[1]
        self.log.append("booking-payment-start")
        return self.r("PAYMENT_PROCESSING")

    async def record_payment(self, *args):
        if len(args) > 1:
            self.payloads["payment-result"] = args[1]
        self.log.append("booking-payment-result")
        return self.r("PAYMENT_PROCESSING")

    async def attach_tickets(self, *args):
        if len(args) > 1:
            self.payloads["tickets"] = args[1]
        self.log.append("booking-tickets")
        return self.r("PAYMENT_PROCESSING")

    async def confirm(self, *args):
        if len(args) > 1:
            self.payloads["confirm"] = args[1]
        self.log.append("booking-confirm")
        return self.r("CONFIRMED")

    async def fail(self, *args):
        if len(args) > 1:
            self.payloads["fail"] = args[1]
        self.log.append("booking-fail")
        return self.r("FAILED")

    async def cancel(self, *args):
        if len(args) > 1:
            self.payloads["cancel"] = args[1]
        self.log.append("booking-cancel-accept")
        return self.r("CANCELLATION_PENDING")

    async def record_compensation(self, *args):
        if len(args) > 1:
            self.payloads["compensation-result"] = args[1]
        self.log.append("booking-comp-result")
        return self.r("CANCELLED")


class Payment:
    def __init__(self, log, status: str = "CAPTURED"):
        self.log = log
        self.status = status
        self.payloads: dict[str, dict] = {}

    async def create(self, *args):
        if args:
            self.payloads["create"] = args[0]
        self.log.append("payment-create")
        return {"paymentId": "p1", "resourceVersion": 1}

    async def authorize(self, *args):
        if len(args) > 1:
            self.payloads["authorize"] = args[1]
        self.log.append("authorize")
        return {"status": "AUTHORIZED", "resourceVersion": 2}

    async def capture(self, *args):
        if len(args) > 1:
            self.payloads["capture"] = args[1]
        self.log.append("capture")
        return {"status": self.status, "resourceVersion": 3}

    async def get(self, *args):
        return {
            "paymentId": "p1",
            "status": "CAPTURED",
            "amountMinor": 300,
            "capturedAmountMinor": 300,
            "refundedAmountMinor": 0,
            "resourceVersion": 3,
        }

    async def cancel(self, *args):
        if len(args) > 1:
            self.payloads["cancel"] = args[1]
        self.log.append("payment-cancel")
        return {}

    async def refund(self, *args):
        if len(args) > 1:
            self.payloads["refund"] = args[1]
        self.log.append("refund")
        return {}

    async def reconcile(self, *args):
        return {}


class Ticket:
    def __init__(self, log):
        self.log = log
        self.payloads: dict[str, dict] = {}

    async def issue(self, *args):
        if args:
            self.payloads["issue"] = args[0]
        self.log.append("issue-ticket")
        return {"tickets": [{"ticketId": "t1"}, {"ticketId": "t2"}]}

    async def get(self, ticket_id: str, ctx):
        return {
            "ticketId": ticket_id,
            "customerId": "cust-1",
            "status": "ISSUED",
            "resourceVersion": 1,
        }

    async def list_booking(self, *args):
        return []

    async def list_customer(self, *args):
        return []

    async def validate(self, *args):
        return {"status": "VALID"}

    async def check_in(self, *args):
        return {"status": "CHECKED_IN"}

    async def cancel(self, *args):
        if len(args) > 1:
            self.payloads["cancel"] = args[1]
        self.log.append("ticket-cancel")
        return {}


class Realtime:
    async def issue_ticket(self, *args):
        return {"ticket": "ws"}


class Subscriber:
    async def publish(self, *args):
        return None
