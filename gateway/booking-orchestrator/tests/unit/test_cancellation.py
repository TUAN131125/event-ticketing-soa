import time,pytest
from app.application.cancellation import CancellationSaga
from app.domain.models import RequestContext,Principal
from tests.fakes import Booking,Payment,Seat,Ticket
@pytest.mark.asyncio
async def test_booking_accepts_cancel_before_compensation():
 log=[];s=CancellationSaga(Booking(log),Payment(log),Seat(log),Ticket(log),None);ctx=RequestContext('c','1'*32,time.monotonic()+5,Principal('u',frozenset(),'cust-1'))
 await s.cancel('b1',{'reason':'USER_REQUEST'},'k',ctx)
 assert log[0]=='booking-cancel-accept'
 assert log[-1]=='booking-comp-result'
