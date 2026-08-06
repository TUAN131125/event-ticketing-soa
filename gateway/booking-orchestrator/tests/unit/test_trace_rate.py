import pytest
from app.security.trace import parse_trace_id
from app.security.rate_limit import SlidingWindowLimiter
from app.domain.errors import EsbError
def test_traceparent_parses_only_trace_id():
 assert parse_trace_id('00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01')=='4bf92f3577b34da6a3ce929d0e0e4736'
@pytest.mark.asyncio
async def test_rate_limit():
 l=SlidingWindowLimiter();await l.check('x',1,60)
 with pytest.raises(EsbError) as e:await l.check('x',1,60)
 assert e.value.status_code==429
