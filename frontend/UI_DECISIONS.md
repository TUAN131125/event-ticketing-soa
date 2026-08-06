# UI decisions

- Identity is accessed only through the ESB `/api/auth/*` façade via an `AuthClient` abstraction. Pages never know the Identity provider URL.
- Access JWTs are held in memory and refresh tokens remain HttpOnly cookies.
  Refresh/logout send the double-submit CSRF header returned through the ESB; the ESB preserves Identity cookies.
- ESB and realtime clients are typed boundaries. There is no runtime mock,
  fake dataset, MSW server, or fake-success fallback in production bundles.
- Server state is owned by TanStack Query; navigation and transient feedback are
  local UI state. Query errors map to shared unavailable/unauthorized/forbidden/
  not-found components.
- Customer pages favor generous whitespace and event imagery; admin pages use a
  denser two-column information hierarchy. Both use the same tokenized indigo
  design system and visible keyboard focus.
- Realtime is best effort. Booking detail always offers REST resynchronization
  and remains correct when the websocket is down.
- Public API paths are configurable because ESB OpenAPI files are placeholders in
  this checkout. Path changes belong in API clients, not page components.
