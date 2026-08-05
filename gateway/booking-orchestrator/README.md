# Booking Orchestrator

Contract-first FastAPI ESB implementing the eight business operations in canonical `contracts/esb-public-api.yaml`. It coordinates provider capabilities through typed ports and never reads provider databases or owns provider domain state.

The booking Saga resolves authoritative Customer/Event data, creates Booking before reserving seats, uses same-key/same-payload `ReserveSeats` replay, distinguishes payment failure from uncertainty, persists evidence, and delivers Notification/Realtime through an outbox. Cancellation is evidence-driven and remains `COMPENSATION_PENDING` until required actions complete.

Production uses PostgreSQL through SQLAlchemy/Alembic. SQLite is supported only
for local tests. Signing keys must be injected through environment or file-based
secret references; the orchestrator never generates fallback keys.

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

## Provider integration credentials

The Seat port remains normalized for the Saga, while `SeatSoapAdapter` translates to the provider-local `urn:event-ticketing:seat-inventory:v1` WSDL/XSD. Configure `ESB_SEAT_SERVICE_TOKEN` and, when the repository layout differs, `ESB_SEAT_PROVIDER_XSD_PATH`. The adapter maps `ttlSeconds` to `holdSeconds`, removes normalized `ticketTypeCode`, validates outbound XML with the provider XSD, and flattens nested provider reservations on ingress.

Realtime outbox delivery uses the provider-native internal authentication headers. Configure `ESB_REALTIME_INTERNAL_SERVICE_TOKEN` and `ESB_REALTIME_CALLER_SERVICE` (default `booking-orchestrator`). Production rejects either provider credential when it is missing or shorter than 32 characters. Credentials are never logged.
