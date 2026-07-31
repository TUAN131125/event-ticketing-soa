# Frontend integration status

## Confirmed runtime contract

The Identity service is executable at `VITE_IDENTITY_API_URL` (or through the
configured gateway transport) and exposes register, login, refresh, logout,
current principal, role administration, JWKS, and liveness/readiness endpoints.
The frontend sends cookies with credentials, keeps the access token in memory,
and uses the CSRF token returned by login/refresh for refresh and logout.

## ESB and realtime status

`contracts/openapi/esb-public-api.yaml` and `contracts/openapi/realtime-service.yaml`
are currently placeholders in this checkout, and the booking orchestrator
endpoints are not implemented. The two web applications therefore use a typed
API boundary with configurable paths and never manufacture events, seats,
bookings, payments, or notifications. A non-2xx network/contract response is
rendered as loading, unavailable, unauthorized, forbidden, or not-found state
with retry where appropriate.

When the ESB contract is published, update the path map in each app's API client
and keep the page/domain types stable. The browser must continue to call only the
public ESB URL; it must never call Seat Inventory SOAP or another private service.

## Environment

```env
VITE_IDENTITY_API_URL=http://localhost:8009
VITE_ESB_API_URL=http://localhost:8000
VITE_REALTIME_WS_URL=ws://localhost:8000/ws
VITE_AUTH_TRANSPORT=direct
```

The applications intentionally remain useful during partial deployment: Identity
can be live while ESB and realtime are unavailable, and the UI communicates that
condition instead of displaying fake success.
