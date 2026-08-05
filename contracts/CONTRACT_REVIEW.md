# Contract implementation review

`/contracts` is the runtime source of truth. This report records implementation drift; it
does not authorize compatibility routes or changes to canonical contracts.

## Resolved in implementation

- Internal REST and SOAP calls use short-lived RS256 Service JWTs with issuer, audience,
  expiration, role, service identity and replay validation.
- Customer, Event, Booking, Payment, Ticket, Notification and Realtime provider routes were
  moved to their canonical paths and operation names; legacy aliases were removed.
- Notification webhook ingestion uses the canonical generic event route, RFC 3339 timestamp,
  HMAC verification and replay protection.
- Realtime accepts ESB-issued, booking-bound, short-lived, single-use WebSocket tickets and
  rejects long-lived access tokens at the WebSocket boundary.
- Customer, Event and Notification expose separate liveness and readiness endpoints.

## Resolved in the canonical contracts

1. `PageMeta` was a self-referencing schema with no concrete definition. No operation in any
   contract returned a pagination envelope, so the dead schema was removed from all seven
   contracts rather than given an unused body. The frontend generator no longer needs its
   deletion workaround, and `validate_contracts.py` now rejects direct and indirect `$ref`
   cycles so the class of defect cannot return.
2. `POST /events/{eventId}/close` is now a canonical Event command. It moves an event from
   `ON_SALE` or `PAUSED` to `ENDED` through the existing state machine and rejects every
   other source state. No parallel `close-sales` route exists.
3. `POST /internal/bookings/{bookingId}/access-decisions` no longer declares
   `Idempotency-Key`, `If-Match` or an `ETag` response header. It is a non-mutating
   authorization query, so the ESB no longer fetches a Booking purely to satisfy a
   precondition. The route is listed in the validator's mutation exclusions.
4. `ConfigureInventory` is a canonical SOAP operation in `seat-inventory.wsdl` and
   `seat-inventory.xsd`. It requires an idempotency key, replays an identical request,
   faults on a reused key with a different payload, refuses to remove or silently modify
   `HELD`/`SOLD` seats, refuses a non-increasing inventory version and runs in one
   transaction. The SOAP layer only validates, maps the DTO and calls the existing
   `configure_inventory` use case. The previously removed `POST /admin/inventory` route was
   not reintroduced.
5. Five operations declared `X-Correlation-ID` twice by referencing both
   `RequiredCorrelationId` and `CorrelationId`. Internal operations now keep only the
   required parameter and the public Realtime ticket operation keeps only the optional one.
   The validator rejects duplicate `(name, in)` parameters after `$ref` resolution.

## Local provisioning

A fresh database is populated only through canonical boundaries. The `seed` Compose profile
runs `scripts/seed_local.py` once: it resolves or creates the demo Event through the Event
API, publishes it, then calls SOAP `ConfigureInventory` with the same `eventId`. It is
opt-in via `SEED_LOCAL_ENABLED`, idempotent, never writes to a service database, never runs
inside a migration and never runs at application startup.

## Runtime defects the restored end-to-end suites exposed

These were found by running the real Compose stack, not by unit tests. Each is fixed and
covered by a regression test.

1. **Seat SOAP was unreachable from the ESB.** `RequestContext` demanded
   `schemaVersion == "1.0"` while `seat-inventory.xsd` types it as `xs:positiveInteger`
   and the ESB adapter sends `1`. Every real ESB-to-Seat SOAP call was rejected. The
   runtime now accepts the canonical value.
2. **Event updates inserted instead of updating.** `PostgresEventRepository.update`
   built a whole new `EventModel` just to reuse its `ticket_types`, cascading a second
   row with the same primary key into the session. Publishing or pausing any event
   failed with a unique-violation. Child rows are now built directly.
3. **Booking transitions crashed on timestamp evidence.** `reservationExpiresAt` and
   `verifiedAt` are parsed into `datetime`, which neither the idempotency hash nor the
   JSONB evidence column could serialize. The payload is now dumped in JSON mode and
   the hash handles timestamps canonically.
4. **A declined payment never compensated.** Payment Service signals a decline as a 402
   business fault, but `_payment_command` only caught `AmbiguousOutcome`, so the fault
   escaped the saga before `ReleaseSeats` and `bookingFail` ran, leaving the seat held
   and the booking un-failed. The decline is now folded back into `PaymentOutcome`.

## Aggregate health

`GET /api/health` now fans out to every dependency and applies one policy. It is
independent of the two process probes:

- `GET /health/live` answers from the process alone: no database, no provider.
- `GET /health/ready` reflects only the ESB's own persistence, so a provider outage
  never removes the ESB from traffic.
- `GET /api/health` probes ESB persistence plus all eight providers.

Customer, Event, Seat Inventory, Booking, Payment and Ticket are critical; Notification
and Realtime are noncritical. All up gives `200 UP`; only noncritical failures give
`200 DEGRADED`; any critical failure gives `503 DOWN`.

Probes run concurrently, each bounded by `ESB_HEALTH_PROBE_TIMEOUT_SECONDS`, with no
retry inside a health request and no background scheduler. One shared `ReadinessProbe`
serves every provider by calling its canonical `GET /health/ready` at the service
origin. Responses carry `status`, `checkedAt` and per-dependency `status`, `latencyMs`
and a stable `errorCode` of `TIMEOUT`, `UNREACHABLE` or `NOT_READY` — never a URL,
hostname, provider message or stack trace.

## Payment outcome classification and reconciliation

The saga distinguishes four outcomes instead of treating every error as a decline:

- **PAID** (`CAPTURED`) — confirm seats, issue tickets, confirm the booking.
- **DECLINED** — a 402 business fault or a `FAILED`/`DECLINED`/`CANCELLED` status;
  release seats, fail the booking, issue nothing. Unchanged from the previous baseline.
- **NOT_DISPATCHED** — an open circuit, an exhausted deadline or a refused connection,
  all of which prove no request byte reached Payment. The ESB releases the seat and
  fails the booking immediately, creates no payment, schedules no reconciliation, and
  records `paymentDispatch: {dispatched: false}` as workflow evidence.
- **UNKNOWN** — the request was written but the answer was lost: a read timeout, a
  connection reset or an ambiguous 5xx. The ESB never guesses. It keeps the seat held,
  issues no ticket, persists a reconciliation record and answers `202` with
  `Location: /api/bookings/{bookingId}` and a configured `Retry-After`.

The adapter separates these by recording dispatch at the transport boundary: connect
failures raise `CommandNotDispatched`, while post-write failures stay ambiguous.

Reconciliation state lives in the ESB's `reconciliation_job` table, which owns the saga.
Migration `0002_reconciliation_lease` adds `deadline_at`, `locked_until` and
`extension_count` plus an index on `(state, next_attempt_at, locked_until)`; the existing
unique constraint on `(workflow_id, kind, idempotency_key)` keeps one active
reconciliation per workflow step. Workers claim jobs with
`SELECT ... FOR UPDATE SKIP LOCKED` and hold a `locked_until` lease, so two replicas
never process one record and a crashed worker's jobs become claimable again.

The worker asks Payment through the canonical `reconcilePayment` operation and never
reads its database. On `CAPTURED` it verifies the reservation over the Seat contract
before confirming; if the seat is gone it refunds instead, leaves explicit evidence and
does not confirm the booking or issue a ticket. On a terminal unsuccessful status it
releases the seat and fails the booking. While the outcome stays unknown it backs off
under a bounded deadline; past the deadline it abandons the job with
`DEADLINE_EXCEEDED` evidence rather than inventing a failure. Every step reuses the
original stable idempotency key, so a replay is deduplicated by the provider.

## Remaining implementation limitations

- Reservation extension during reconciliation is not implemented. The ESB has no
  `ExtendReservation` adapter, and the contract makes extension optional, so a seat is
  held only for its original TTL. This bounds seat holding but means a long
  reconciliation can outlive the reservation, which is why the refund path exists.
- A payment frozen mid-create resumes as `PENDING`, which is not authoritative. The
  worker correctly keeps polling until its deadline; such a booking is only settled by a
  later capture or by deadline abandonment, not by the worker alone.
- Notification delivery uses the repository's local delivery provider; external email
  transport is intentionally outside the local Compose baseline.
- `event-service` migration `0001_initial_schema` still inserts the `EV001` demo row. It
  predates the seed job and is left untouched because rewriting an applied migration is out
  of scope; `seed_local.py` is idempotent either way and uses one `eventId` for both Event
  and Seat.
- No legacy frontend admin mutations, direct Seat/Payment/Ticket provider calls, or
  undocumented ESB routes are retained.
- Everything above was verified against the local Docker Compose stack only. Neither the
  GitHub Actions pipeline nor an AWS deployment has been executed for these changes, so
  nothing here should be read as production-ready.
