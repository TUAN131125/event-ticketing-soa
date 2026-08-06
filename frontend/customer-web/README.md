# Customer Web

Customer Web implements UI-01 đến UI-09 và UI-12. All browser HTTP requests, including authentication, go through the ESB. Identity remains authoritative behind the ESB authentication façade; the browser never calls Identity or any business service directly.

## Route chính

- `/events`, `/events/:eventId` — browse/detail.
- `/events/:eventId/seats` — seat-map selection through the planned ESB projection.
- `/checkout/contact`, `/checkout` — validated contact draft and mock payment choice.
- `/bookings`, `/bookings/:bookingId`, `/bookings/:bookingId/status` — history/detail/status/cancellation.
- `/tickets`, `/tickets/:ticketId` — owner-scoped ticket/QR projection.

## Configuration

```dotenv
VITE_ESB_API_URL=http://localhost:8000
VITE_ESB_CANCEL_REASON_ENABLED=false
```

The access token stays in memory. Refresh/CSRF cookies originate from Identity and are preserved by the ESB auth façade. Customer name/email/phone in UI-04 are not persisted to browser storage.

## Verification

```bash
npm ci
npm run typecheck
npm test
npm run build
npm run e2e
```

Missing future ESB façades are shown explicitly as integration-pending states; the UI never fabricates seat availability, ticket status or QR data.
