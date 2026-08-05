# Frontend integration status

## Confirmed runtime contract

The Identity service is executable at `VITE_IDENTITY_API_URL` (or through the
configured gateway transport) and exposes register, login, refresh, logout,
current principal, role administration, JWKS, and liveness/readiness endpoints.
The frontend sends cookies with credentials, keeps the access token in memory,
and uses the CSRF token returned by login/refresh for refresh and logout.

## ESB and realtime status

`contracts/esb-public-api.yaml`, `contracts/realtime-service.openapi.yaml` and
`contracts/realtime-service.asyncapi.yaml` are the canonical target contracts.
The two web applications retain a typed API boundary and never manufacture
events, seats, bookings, payments, or notifications. Known route, Money and
WebSocket-frame drift is tracked in `contracts/CONTRACT_REVIEW.md`; frontend
behavior is not changed by the contract-only alignment.

When implementing the remaining alignment, update the path map and Money types
against the canonical files. The browser must call only the public ESB URL for
HTTP business operations and use an ESB-issued one-time ticket for Realtime; it
must never call Seat Inventory SOAP or another private service.

## Environment

```env
VITE_IDENTITY_API_URL=http://localhost:8009
VITE_ESB_API_URL=http://localhost:8000
VITE_REALTIME_WS_URL=ws://localhost:8008
VITE_AUTH_TRANSPORT=direct
```

The applications intentionally remain useful during partial deployment: Identity
can be live while ESB and realtime are unavailable, and the UI communicates that
condition instead of displaying fake success.
