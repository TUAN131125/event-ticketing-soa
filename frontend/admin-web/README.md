# Admin Web

Admin Web implements UI-10 Event administration and UI-11 Ticket check-in, plus aggregate health and workflow traces. All browser HTTP requests, including authentication, go through the ESB. Identity remains authoritative behind the ESB auth façade.

## Route

- `/overview` — health and integration map.
- `/events` — Event management list.
- `/events/new` — create Event.
- `/events/:eventId/edit` — update Event/ticket types.
- `/check-in` — validate QR and check in Ticket.
- `/traces` — workflow trace by Correlation ID.

The Admin Web does not expose an owner-scoped Booking lookup/cancel screen. Booking history and cancellation remain in Customer Web; adding an admin-wide Booking operation would require a separately authorized ESB contract and is outside UI-01–UI-12.

## Configuration

```env
VITE_ESB_API_URL=http://localhost:8000
VITE_ESB_CANCEL_REASON_ENABLED=false
```

## Verification

```bash
npm ci
npm run typecheck
npm test
npm run build
npm run e2e
```
