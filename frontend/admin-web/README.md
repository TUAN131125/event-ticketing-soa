# Admin Web

The operations console is a React/Vite application. It uses Identity for authentication and the ESB public API for every operational read or command. It does not call internal services directly and it never supplies local fake data when the ESB is unavailable.

## Run locally

```bash
npm install
cp .env.example .env.local
npm run dev
```

Required environment:

```env
VITE_IDENTITY_API_URL=http://localhost:8009
VITE_ESB_API_URL=http://localhost:8000
VITE_AUTH_TRANSPORT=direct
```

`VITE_AUTH_TRANSPORT=gateway` keeps the same client boundary and is available when the gateway exposes `/auth/*` routes. A browser refresh restores the session through the HttpOnly refresh cookie; access tokens remain in memory.

## Verification

```bash
npm run typecheck
npm test
npm run build
npm run e2e
```

The gateway currently has incomplete public contracts, so list and detail screens explicitly show an unavailable/not-found/forbidden state rather than inventing records.
