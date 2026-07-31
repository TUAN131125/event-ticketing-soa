# Customer Web

The customer-facing Evently application. It uses the Identity REST API for account/session operations and the ESB public API for events, seat inventory and bookings. It never calls internal services or SOAP directly.

## Configuration

Copy `.env.example` to `.env.local`:

```dotenv
VITE_IDENTITY_API_URL=http://localhost:8009
VITE_ESB_API_URL=http://localhost:8000
VITE_REALTIME_WS_URL=ws://localhost:8007
VITE_AUTH_TRANSPORT=direct
```

`direct` points authentication requests at `VITE_IDENTITY_API_URL`; `gateway` points `/auth/*` at the ESB URL. The access token stays in memory. Refresh and CSRF cookies are managed by Identity, while the CSRF token is kept in session storage for the browser session. A reload restores the session through `/auth/refresh`.

## Development

From this directory (or the frontend workspace):

```bash
npm install
npm run dev
npm run typecheck
npm test
npm run build
```

When the ESB is unavailable the UI deliberately shows loading, retry, unavailable, unauthorized, forbidden or not-found states. It does not fabricate events, seats or bookings. Browser smoke tests cover these failure-safe states without mocking production runtime.

## Docker

```bash
docker build -f customer-web/Dockerfile -t evently-customer-web .
docker run --rm -p 8080:80 evently-customer-web
```
