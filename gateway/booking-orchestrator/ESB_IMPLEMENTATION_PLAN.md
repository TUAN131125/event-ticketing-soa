# ESB implementation plan

## 12.1 Contract freeze

- Freeze ID: `event-ticketing-contracts-v1.0.0`
- Catalog digest: `6fea9810b380cd94a00fa2a5b611e70c01d8db1c41b6ca886b303a9395d408a6`
- Manifest digest: `f93f3c05837b542d028cc9b672c00f41cc1a9915ab32156e735dae4175abc746`
- Canonical source: root `contracts/`, locked by `contracts/FREEZE.lock.yaml`.
- The ESB implementation prompt consumes this freeze and must not edit canonical contracts. Contract changes require a separate governed contract change and a new freeze.
- `contracts/**` is the sole semantic and wire authority. `ESB_DEPENDENCIES.yaml` is a derived orchestration design only: it may reconcile call ordering and failure planning, but it is not a canonical contract and cannot override an OpenAPI, WSDL, XSD or shared schema.

The derived booking creation order is:

```text
CheckAvailability
→ createBooking
→ ReserveSeats (bookingId from createBooking output)
→ bookingReservation
→ createPayment
→ bookingPaymentStarted
→ authorizePayment
→ capturePayment
→ bookingPaymentResult
→ issueTickets
→ bookingTickets
→ ConfirmSeats
→ bookingConfirm
```

Failure planning follows the frozen provider capabilities: `createBooking` failure stops without compensation; a determined `ReserveSeats` failure records `bookingFail` without Payment, Ticket or `ReleaseSeats`; an ambiguous reserve result replays `ReserveSeats` with the same idempotency key and identical payload while deadline remains, and `GetReservation` is used only after a `reservationId` is known from a response or persisted evidence. If bounded replay remains unknown, Booking stays `PENDING` and later replay/reconciliation retains the same key. Failure to record `bookingReservation` after a successful reserve schedules `ReleaseSeats` before `bookingFail`, remaining `COMPENSATION_PENDING` until release evidence exists. Payment `UNKNOWN` remains on reconciliation with no Ticket, seat/booking confirmation or unsafe release.

## 12.2 Proposed module boundaries

```text
api/                 HTTP transport, request/response translation
application/         use cases and Saga coordinators
domain/              workflow state, evidence and policy types
ports/               provider/repository/clock interfaces
adapters/rest/       canonical REST provider adapters
adapters/soap/       canonical Seat WSDL adapter and fault mapping
security/            browser JWT verification and service credentials
resilience/          deadlines, retries, circuit state and idempotency policy
observability/       safe logs, metrics and correlation/trace propagation
persistence/         workflow, idempotency and trace repositories
```

`domain/` and `application/` must not import FastAPI, HTTPX or Zeep. Transport libraries remain adapter details behind ports.

## 12.3 Required ports

- `CustomerPort`: resolve identity mapping and read active customer.
- `EventPort`: list/detail and sale eligibility with authoritative pricing.
- `SeatPort`: canonical SOAP availability, reservation, confirmation, release and reservation reads.
- `BookingPort`: authoritative booking commands, reads, evidence transitions and access decisions.
- `PaymentPort`: create, authorize, capture, read, refund and reconcile.
- `TicketPort`: issue, query by booking and cancel.
- `NotificationPort`: non-critical side-effect port; failure never rolls back Booking.
- `RealtimePort`: non-critical side-effect port; failure leaves REST as authoritative fallback.
- `WorkflowRepository`: durable Saga step/evidence state; no provider data ownership.
- `IdempotencyRepository`: public request hash, workflow identity and recorded result.
- `TraceRepository`: ESB workflow evidence for `/api/traces/{correlationId}` only.
- `Clock`: deadlines, ticket `iat`/`exp` and deterministic temporal tests.

## 12.4 Vertical-slice implementation order

| Slice | Public operation | Ports | Canonical provider operations | Consumer tests | Completion evidence |
|---|---|---|---|---|---|
| 1 — Event list/detail routing | `publicListEvents`, `publicGetEvent` | EventPort | `listEvents`, `getEvent` | Event resolution and `ESB-EVENT-READ-001` | Public schemas validate; no Seat/Booking/Payment call |
| 2 — Booking get + access decision | `publicGetBooking` | BookingPort, Identity/JWKS security | `decideBookingResourceAccess`, `getBooking`, `getIdentityJwks` | access-order and deny-before-disclosure tests | Owner/admin allowed; deny reveals no booking |
| 3 — Booking creation happy path with test doubles | `placeBooking` | CustomerPort, EventPort, SeatPort, BookingPort, PaymentPort, TicketPort, repositories, Clock | `CheckAvailability`, `createBooking`, `ReserveSeats` using returned `bookingId`, `bookingReservation`, then Payment/Ticket/confirm sequence | `ESB-BOOKING-SUCCESS-001`, idempotency, correlation | Recorded 201 only with payment/seat/ticket evidence |
| 4 — Seat SOAP adapter and fault mapping | `placeBooking` | SeatPort, BookingPort | `CheckAvailability`, `ReserveSeats`, same-key `ReserveSeats` replay, conditional `GetReservation`, `ReleaseSeats`; reserve failure records Booking failure | seat unavailable, `ESB-RESERVE-FAIL-AFTER-BOOKING-001`, `ESB-RESERVE-UNKNOWN-001`, SOAP fault mapping | No pre-booking reserve; ambiguous reserve replays the identical request/key; `GetReservation` requires a known `reservationId`; safe ErrorResponse |
| 5 — Payment failure + ReleaseSeats Saga | `placeBooking` | PaymentPort, SeatPort, BookingPort | `authorizePayment`, `capturePayment`, `bookingPaymentResult`, `ReleaseSeats`, `bookingFail` | `ESB-PAYMENT-FAILED-001` | No ticket; release/failure evidence persisted |
| 6 — Payment UNKNOWN + reconciliation | `placeBooking` | PaymentPort, BookingPort, WorkflowRepository | `capturePayment`, `bookingPaymentResult`, `reconcilePayment` | `ESB-PAYMENT-UNKNOWN-001` | 202/pending; no blind charge retry, ticket, confirm or unsafe release |
| 7 — Ticket/Seat/Booking confirmation evidence | `placeBooking` | TicketPort, SeatPort, BookingPort | `issueTickets`, `bookingTickets`, `ConfirmSeats`, `bookingConfirm` | happy path and after-capture failure | Confirm requires all evidence; failures persist `COMPENSATION_PENDING` |
| 8 — Cancellation compensation | `publicCancelBooking` | BookingPort, TicketPort, PaymentPort, SeatPort | access/get, list/cancel ticket, get/refund payment, get/release reservation, booking cancel | `ESB-CANCEL-001` | `CANCELLED` only after required compensation evidence |
| 9 — Notification/Realtime side effects | `placeBooking` post-commit | NotificationPort, RealtimePort | `receiveEventWebhook`, `ingestRealtimeStatusEvent` | notification failure and correlation scenarios | Confirmed result survives either side-effect failure |
| 10 — Health, trace and resilience hardening | `aggregateHealth`, `getWorkflowTrace`, `issueRealtimeWebSocketTicket` | TraceRepository, Clock, BookingPort, security/resilience ports | access decision; no provider DB read | realtime ticket, freeze, retry mutation tests | Shallow health, evidence trace, signed ≤60s single-use ticket |

### Provider readiness assessment

Runtime was inspected only as evidence. Every readiness status below is backed by a concrete path or symbol. `DRIFT` or `MISSING` is an integration prerequisite; it does not authorize private/runtime-only paths or canonical changes. Port/test-double slices may proceed before provider alignment. Existing Booking Orchestrator remains `MISSING` while its runtime source consists only of placeholders.

| Provider | Required canonical operations | Runtime status | Evidence path or symbol | Blocking for which slice | Action |
|---|---|---|---|---|---|
| Customer | mapping resolve/link/unlink; customer get | DRIFT | `services/customer-service/app/api/router.py::api_router` includes public resources/admin/health only; no `/internal/identity-mappings` route | 2, 3 | Add provider alignment for internal mapping, one-to-one/audit/inactive semantics and canonical paths before integration |
| Event | list, detail, sale eligibility | DRIFT | `services/event-service/app/api/v1/resources.py::router` provides event resources but no `getSaleEligibility` operation | 1, 3 | Align `/sale-eligibility`, status/price response and canonical error envelope |
| Seat Inventory | 8 SOAP operations; v1 namespace/actions; `SeatServiceFault` | DRIFT | `services/seat-inventory-service/contracts/seat-inventory.wsdl` uses `urn:event-ticketing:seat-inventory:v1/*` actions and `SeatInventoryFault` | 4, 5, 7, 8 | Align runtime WSDL namespace `urn:event-ticketing:seat:v1`, actions and fault name before adapter integration |
| Booking | 10 business operations, access decision, seven-state/evidence model | DRIFT | `services/booking-service/app/api/v1/resources.py::router` and `admin.py::router` have no `/internal/bookings/{bookingId}/access-decisions` operation | 2, 3, 5, 6, 7, 8 | Add missing transition/access operations and align runtime state model to canonical evidence semantics |
| Payment | create/get/authorize/capture/cancel/refund/callback/reconcile including `UNKNOWN` | DRIFT | `services/payment-service/app/api/v1/admin.py::reconcile` exists, but canonical callback/UNKNOWN evidence is not exposed consistently across `resources.py` and `admin.py` | 3, 5, 6, 8 | Align `UNKNOWN`, callback and reconciliation semantics; prove idempotency before integration |
| Ticket | issue/get/by-booking/validate/check-in/cancel/reissue; `ISSUED` state | DRIFT | `services/ticket-service/app/api/v1/resources.py::router` and `admin.py::router` do not expose the canonical `/tickets:issue` and `/bookings/{bookingId}/tickets` pair | 3, 7, 8 | Align issue/by-booking paths and runtime state with canonical `ISSUED` evidence |
| Notification | generic signed `POST /webhooks/events` | DRIFT | `services/notification-service/app/api/v1/webhooks.py::router` is present but does not implement the canonical generic signed ingress schema/security | 9 | Replace/augment event-specific runtime hooks with canonical signed generic ingress |
| Realtime Status | internal status ingestion and signed one-time-ticket WebSocket protocol | DRIFT | `services/realtime-status-service/app/main.py::create_app` exposes `/internal/status-events`, while `app/websocket/endpoint.py` implements a different JWT/access flow than the signed single-use ticket protocol | 9, 10 | Align service JWT replay policy and signed single-use ticket flow before live integration |
| Identity | register/login/refresh/logout/me/admin roles/JWKS and canonical claims | PRESENT | `services/identity-service/app/main.py::create_app`, `app/api/v1/resources.py::create_resources_router`, `app/api/v1/admin.py::create_admin_router` and `/.well-known/jwks.json` route | none for contract-first slices | Retain as evidence; add provider conformance test before live integration |
| Existing Booking Orchestrator | eight public operations and canonical Sagas | MISSING | `gateway/booking-orchestrator/app/main.py`, `app/api/*.py` and `app/orchestration/*.py` are placeholder modules with no canonical route/Saga implementation | all runtime integration slices | Build the canonical implementation behind ports and do not reuse provider-private paths |

Readiness totals before Prompt 4 implementation: `PRESENT=1`, `DRIFT=8`, `MISSING=1`, `UNKNOWN=0`.

## 12.5 Deferred work

Prompt 3 does not implement provider runtime alignment, ESB source, Docker integration, AWS, queue infrastructure, production retry durations, a distributed tracing backend, UI, performance tests or production-readiness evidence. Notification and Realtime transport infrastructure remains a later implementation choice; their contract-level failure isolation is already fixed.
