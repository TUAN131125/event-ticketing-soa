# ESB / Booking Orchestrator 2.2

This directory is a repository overlay for `gateway/booking-orchestrator`. It preserves the existing ESB API and adds the façades required by the documented frontend and project scope.

## Architectural boundary

The ESB owns:

- logical service discovery and routing;
- REST-to-SOAP mediation for Seat Inventory;
- transport-level validation and canonical message transformation;
- booking and cancellation orchestration;
- workflow evidence, idempotency and reconciliation;
- ingress authentication, role and ownership checks;
- dependency deadlines, bounded retries, bulkheads and circuit breaking;
- transactional outbox dispatch, dead-lettering and correlation/trace propagation;
- public error normalization and aggregate readiness.

Event, Customer, Seat, Booking, Payment and Ticket services remain authoritative for their own data, state machines and domain rules. The ESB does not choose a ticket type, invent a price, decide seat availability, validate QR signatures, own customer profile data or calculate a refund amount.

## Correct booking workflow

```text
Resolve identity → Customer
Get Event + sale eligibility + Seat map
Map authoritative seat/ticket-type and Event price evidence
Create Booking
Read authoritative total/currency from Booking
ReserveSeats
Create/Authorize/Capture Payment
Record Payment evidence
ConfirmSeats
Record confirmed-reservation evidence
IssueTickets
AttachTickets
ConfirmBooking
Publish booking.confirmed and booking.status through the outbox
```

The corrected ordering is:

```text
Payment CAPTURED → ConfirmSeats → IssueTickets → AttachTickets → ConfirmBooking
```

A provider timeout after a potentially committed payment command becomes `PAYMENT_UNKNOWN` and enters reconciliation; it is never converted blindly to `FAILED`.

## Public façade

The public contract includes:

- event list/detail and seat-map projection;
- authenticated booking create/list/detail/cancel;
- ticket wallet, booking tickets and ticket detail/QR projection;
- authenticated Customer onboarding/profile and consent façade;
- ADMIN event lifecycle façade;
- ADMIN Seat Inventory read/configure façade translated to SOAP;
- CHECKIN_STAFF or ADMIN validate/check-in façade;
- one-time Realtime WebSocket ticket issuance;
- aggregate health and workflow trace endpoints.

Identity is private behind the ESB authentication façade described in `ADR-ESB-001-IDENTITY-VIA-ESB.md`. The browser calls `/api/auth/*` on port 8000; the ESB forwards only the canonical Identity operations and preserves refresh/CSRF cookies. Direct browser calls to port 8009 are forbidden. Realtime WebSocket access is disabled in the current frontend build; REST polling through the ESB remains authoritative until a gateway WebSocket route is approved.


### Authentication boundary

The public browser contract is `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh`, `/api/auth/logout` and `/api/auth/me`. Identity Service remains authoritative for passwords, access JWTs, refresh-token rotation, roles, lockout and JWKS. The ESB does not issue tokens or validate passwords. It only forwards the approved calls, rewrites Identity cookie `Path=/auth` to `Path=/api/auth`, preserves multiple `Set-Cookie` headers and normalizes transport failures.

For direct host execution, use `.env.host.example`; for Docker networking, use `.env.docker.example`. Copying a file is not enough by itself—the Uvicorn command must include `--env-file`.

## OpenAPI contract workflow

FastAPI route declarations and Pydantic models generate the actual runtime OpenAPI. The application does **not** replace `app.openapi()` with a YAML file.

```bash
# Export only the runtime snapshot used for parity checks.
PYTHONPATH=. python scripts/export_openapi.py

# Explicit maintainer action when an approved contract change is intentional.
PYTHONPATH=. python scripts/export_openapi.py --update-canonical
```

Contract tests compare the unmodified FastAPI-generated document with:

- repository canonical: `contracts/esb-public-api.yaml`;
- runtime snapshot: `contracts/generated/esb-runtime.openapi.yaml`;
- gateway mirror: `gateway/booking-orchestrator/contracts/esb-public-api.yaml`.

Every JSON response is validated against its Pydantic response model before a `JSONResponse` is created. Canonical headers such as `ETag`, `Location` and `Retry-After` are declared and emitted by the relevant endpoints.

## PostgreSQL schema lifecycle

Production schema is migration-owned. The runtime does not call `metadata.create_all()` for PostgreSQL.

Apply migrations before application startup. Migration `migrations/versions/0002_esb_refactor.sql` creates the exact tables used by the repository:

- `esb_workflows_v2`;
- `esb_outbox_v2`;
- `esb_ws_ticket_v2`.

Startup fails fast when these tables are absent. SQLite remains available only for local/unit-test execution.

## Local start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.host.example .env
uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --env-file .env
```

Production validation requires PostgreSQL, explicit CORS origins, Identity JWKS, RS256 internal-service and WebSocket-ticket keys, a Notification webhook secret and disabled API documentation.

## Verification

```bash
python -m compileall -q app scripts tests
pytest -q
PYTHONPATH=. python scripts/export_openapi.py
```

From the repository `frontend` directory:

```bash
python scripts/generate_esb_types.py
python scripts/verify_esb_consumer_contract.py
npm run typecheck
npm run test
npm run build
```

The Python fallback generator/verifier is intended for restricted environments. Normal development and CI should still run the npm generator, TypeScript compiler, Vitest and Playwright.

## Docker

```bash
docker build -t event-ticketing-esb:2.2 .
docker run --rm -p 8000:8000 --env-file .env.docker.example event-ticketing-esb:2.2
```

The image runs as non-root user `10001` and exposes `/health/live` for container liveness. Aggregate readiness checks the ESB database and configured dependencies.
