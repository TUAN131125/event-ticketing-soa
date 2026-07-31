# Event Ticketing web applications

This directory is an npm workspace containing the customer-facing booking
application, the administrator console, and the shared accessible design system.

## Local development

```powershell
cd frontend
npm install
npm run typecheck
npm run test
npm run build
```

Run an application independently with `npm run dev --workspace customer-web`
or `npm run dev --workspace admin-web`.

Copy each app's `.env.example` to `.env.local` and set the public Identity,
ESB, and realtime URLs for the environment. The applications do not ship a
mock API and do not call private services directly. ESB/realtime being offline
is represented by an explicit unavailable state in the UI.

## Production containers

Both apps have a multi-stage Dockerfile that builds the Vite bundle and serves it
with nginx using SPA fallback. Runtime API URLs are supplied at build time via
Vite environment variables; do not put secrets in the frontend image.
