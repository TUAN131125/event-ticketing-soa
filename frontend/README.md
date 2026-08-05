# Event Ticketing web applications

This npm workspace contains:

- `customer-web`: restored customer booking UI adapted to the current ESB contract.
- `admin-web`: contract-safe operations console for the public admin/observability capabilities that
  currently exist.
- `shared-ui`: shared accessible components, design tokens and the generated ESB, Identity and
  Realtime contract types.

## Local development

```powershell
cd frontend
npm ci
npm run generate:contracts
npm run lint
npm run typecheck
npm run test
npm run build
```

`npm run generate:contracts` regenerates `shared-ui/src/generated/` from `/contracts` and is
deterministic: running it twice produces no diff. Generated files are never edited by hand.

Run either application independently:

```powershell
npm run dev --workspace @event-ticketing/customer-web
npm run dev --workspace @event-ticketing/admin-web
```

Copy each application's `.env.example` to `.env.local`. The default local ports match the current
Compose source: Identity `8009`, ESB `8000`, Realtime `8008`, customer web `3000` and admin web
`3001`.

## Contract rule

HTTP business calls go only to the ESB public API (`8000`), authentication calls only to Identity
(`8009`) and the booking status stream only to Realtime (`8008`). The frontend never calls the
private service ports `8001`–`8007`, never invents missing API responses and never treats browser
state as authoritative.

See `INTEGRATION_STATUS.md` for the exact restored features and the current contract gaps.

## Production containers

Both applications have multi-stage Dockerfiles that build the Vite bundle and serve it with nginx
SPA fallback. Public URLs are Vite build arguments; no secret may be embedded in a frontend image.
