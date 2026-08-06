import time

import pytest

from app.application.cancellation import CancellationSaga
from app.domain.errors import Conflict
from app.domain.models import Principal, RequestContext
from tests.fakes import Booking, Customer, Payment, Seat, Ticket


@pytest.mark.asyncio
async def test_rejected_booking_cancellation_causes_no_compensation_side_effect():
    log = []
    class RejectingBooking(Booking):
        async def cancel(self, *args):
            self.log.append("booking-cancel-rejected")
            raise Conflict("BOOKING_INVALID_TRANSITION", "Cancellation is not allowed")
    saga = CancellationSaga(RejectingBooking(log), Payment(log), Seat(log), Ticket(log), Customer())
    context = RequestContext("c", "1" * 32, time.monotonic() + 5, Principal("u", frozenset(), "cust-1"))
    with pytest.raises(Conflict):
        await saga.cancel("b1", {"reason": "USER_REQUEST"}, "idem-cancel", context)
    assert log == ["booking-cancel-rejected"]
