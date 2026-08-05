# Frontend integration status

## Restoration source

The visual customer application was restored from the frontend tracked in the repository history
(the same frontend family currently visible on GitHub) and then adapted to the uncommitted backend
and contract source in this bundle. The administrator application uses the contract-safe console
variant because the current ESB public contract does not publish the old admin CRUD/list routes.

## Canonical HTTP boundaries

The frontend uses these current contracts as its source of truth:

- `contracts/identity-service.yaml` for register, login, refresh, logout, current user and role change.
- `contracts/esb-public-api.yaml` for event list/detail, booking create/get/cancel, aggregate health,
  workflow trace and one-time Realtime WebSocket tickets.
- `contracts/realtime-service.asyncapi.yaml` for the browser WebSocket message flow.

`npm run generate:contracts` regenerates every file under `shared-ui/src/generated/`:

| File | Source |
| --- | --- |
| `esb-public-api.ts` | `contracts/esb-public-api.yaml` |
| `identity-service.ts` | `contracts/identity-service.yaml` |
| `realtime-service.ts` | `contracts/realtime-service.openapi.yaml` |
| `realtime-messages.ts` | `contracts/realtime-service.asyncapi.yaml` message payloads |

Customer and admin API clients import these generated types instead of maintaining duplicate wire
models. The generator is deterministic; a second run produces no diff.

## Deliberate compatibility changes

1. Event listing consumes the ESB's plain JSON array. Search and pagination are performed only in
   the browser because the public contract currently has no query parameters.
2. Booking creation sends exactly `customerId`, `eventId`, `seatIds` and `paymentMethodToken`, with
   `Idempotency-Key` and an access token.
3. Booking cancellation first obtains the authoritative `ETag`, then sends `If-Match` and a new
   `Idempotency-Key`.
4. Realtime authentication uses `POST /api/realtime/ws-tickets`; the signed ticket is sent in the
   first WebSocket `authenticate` frame and never placed in a URL, header or subprotocol. Every
   reconnect fetches a new single-use ticket and reloads the authoritative booking over REST.
   Heartbeats are answered with the contract `heartbeat_ack` frame.
5. The previous seat-map/reservation, booking-list, ticket-detail, payment-list and notification-list
   calls were removed because those operations are not present in the current public ESB contract.
6. `POST /api/bookings` distinguishes `201` from `202`. A `202` means the payment outcome is unknown
   and the ESB owns a reconciliation job: the UI moves to the booking status screen, shows that the
   outcome is being reconciled, and polls `GET /api/bookings/{bookingId}` at the server's
   `Retry-After` interval. The booking command is never resent and no client-side status is invented.

## UI behavior for contract gaps

- Seat selection is an explicit `seatIds` entry screen. The browser does not claim availability;
  Seat Inventory remains authoritative during booking orchestration.
- Identity `userId` is not treated as a Customer Service `customerId`. Checkout asks for the current
  customer ID because `PlaceBookingRequest` still requires it. Ownership is not decided by that
  value: the ESB resolves the authoritative customer from the signed-in identity subject's Customer
  mapping, so a booking fails with `IDENTITY_NOT_MAPPED` until that mapping exists.
- Booking statuses are rendered from a single contract-derived table. The known values are the ones
  the Realtime projection enumerates; any other value degrades to a neutral “service remains
  authoritative” presentation instead of being guessed at. No client-only status such as
  `PENDING_RECONCILIATION` exists.
- Tickets are only linked from a `CONFIRMED` booking.
- “My bookings” stores only recently used booking IDs for navigation. Each detail view reloads the
  authoritative state from `GET /api/bookings/{bookingId}`.
- Ticket IDs are displayed from `BookingResult`; QR content is not fabricated while the ESB has no
  public ticket-detail endpoint.
- The admin console exposes only aggregate health, event reads, booking lookup/cancel and workflow
  trace lookup. Everything else it could plausibly do — user and role administration, event
  authoring, provider listings — is listed on screen as not supported by the current contract rather
  than being faked or routed to a private service.

## Environment

```env
VITE_IDENTITY_API_URL=http://localhost:8009
VITE_ESB_API_URL=http://localhost:8000
VITE_REALTIME_WS_URL=ws://localhost:8008
```

These are Vite build arguments supplied by Compose (`customer-web` on `3000`, `admin-web` on
`3001`). No service URL is hardcoded in the application source.

The browser calls Identity only for authentication and the ESB for all business operations. It never
calls Customer, Event, Seat, Booking, Payment, Ticket or Notification services directly.
