# Booking Orchestrator

Contract-first FastAPI ESB implementing the eight public operations frozen in `contracts/openapi/esb-public-api.yaml`. It coordinates provider capabilities through typed ports and never reads provider databases or owns provider domain state.

The booking Saga resolves authoritative Customer/Event data, creates Booking before reserving seats, uses same-key/same-payload `ReserveSeats` replay, distinguishes payment failure from uncertainty, persists evidence, and delivers Notification/Realtime through an outbox. Cancellation is evidence-driven and remains `COMPENSATION_PENDING` until required actions complete.

Production uses PostgreSQL through SQLAlchemy/Alembic. SQLite is supported only for local tests. Signing keys are injected through environment/secret references; development keys are ephemeral and never stored.

```bash
python -m pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```bash
python -m pytest ../../tests/unit/esb -q
python -m pytest ../../tests/integration/esb -q
```

Provider runtime drift remains a live-integration prerequisite. Controlled test doubles validate the frozen contract-level orchestration without claiming live provider integration.
