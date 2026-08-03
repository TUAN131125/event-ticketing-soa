# Realtime Status WebSocket protocol v1.0.0

This is the official clean-slate v1 protocol. Realtime Status is a best-effort UX projection, never the authoritative Booking state, never a durable event store and never part of the booking critical path. The authoritative fallback is `GET /api/bookings/{bookingId}`.

## Signed ticket issuance

```text
Browser user JWT
→ POST /api/realtime/ws-tickets at ESB with {bookingId}
→ ESB calls POST /internal/bookings/{bookingId}/access-decisions
→ Booking resolves the Customer-owned identitySubject ↔ customerId mapping
→ ESB signs and returns a one-time JWT/JWS ticket in the response body
```

Only `booking-orchestrator` issues the ticket. Required signed claims are:

```text
iss       = booking-orchestrator
aud       = realtime-status-service
sub       = verified identity subject
bookingId = booking allowed by the Booking access decision
scope     = booking:status:read
iat
exp       = no more than 60 seconds after iat
jti       = unique ticket identifier
```

The ticket contains no email, phone, customer profile, raw access token or unnecessary customerId. It is signed, single-use, non-refreshable and never logged. A ticket or long-lived browser access token in a WebSocket URL or query string is forbidden.

## Connection and authentication

Endpoint:

```text
WS /ws/bookings/{bookingId}
```

The browser opens the WebSocket without URL credentials and sends this frame within five seconds:

```json
{"type":"authenticate","ticket":"signed-single-use-ticket"}
```

Realtime verifies signature, issuer, audience, expiry, scope and that the signed `bookingId` equals the WebSocket path. It then atomically consumes `jti`. Each `jti` can authenticate successfully exactly once. Invalid, expired, mismatched or reused tickets are rejected, and the raw ticket is never logged.

## State machine

```text
CONNECTED_UNAUTHENTICATED
  -- authenticate(valid signed ticket; jti consumed once; within 5s) --> AUTHENTICATED
AUTHENTICATED
  -- subscribe(ticket-bound bookingId) ------------------------------> SUBSCRIBED
SUBSCRIBED
  -- unsubscribe ----------------------------------------------------> AUTHENTICATED
ANY STATE
  -- timeout, denial, disconnect or shutdown ------------------------> CLOSED
```

No booking status is sent and subscription is forbidden before authentication. Status messages are sent only in `SUBSCRIBED`. Reconnect requires a new ticket; tickets cannot be refreshed. Multiple tabs require separate tickets and remain subject to connection limits.

## Status and resynchronization

- Status frames conform to `status-message.schema.json` and are scoped to the ticket-bound booking.
- `messageId` provides bounded short-term deduplication and `sequence` increases monotonically per booking.
- Duplicate or stale messages are not rebroadcast; a gap triggers `resync_required`.
- Reconnect or unavailable history requires `GET /api/bookings/{bookingId}`.
- Delivery is best effort; no exactly-once or durable replay guarantee is made.

## Internal producer authentication

`POST /internal/status-events` accepts only `InternalServiceJwt`. Required claims are `iss`, `sub`, `aud`, `iat`, `exp` and `jti`; `aud` is `realtime-status-service`, `sub` must be allow-listed and replayed `jti` values are rejected. Browser JWTs are forbidden. Deployment mTLS may supplement but does not replace this contract.

## Close codes

The stable registry is `close-codes.yaml`. Standard codes keep their RFC-defined meaning. Authentication, heartbeat, connection-limit and restart closures never expose credential or ownership data.
