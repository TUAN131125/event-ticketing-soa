import pytest
from app.domain.models import OutboxMessage
from app.persistence.repositories import InMemoryRepository
from app.workers.outbox import OutboxWorker
class Bad:
 async def publish(self,*a):raise RuntimeError('bad destination')
@pytest.mark.asyncio
async def test_dead_letters_after_max_attempts():
 r=InMemoryRepository();m=OutboxMessage('1','x',{});await r.add(m);w=OutboxWorker(r,Bad(),max_attempts=2)
 await w.run_once();m.next_attempt_at=0;await r.save_message(m);await w.run_once();assert m.state=='DEAD_LETTER'
