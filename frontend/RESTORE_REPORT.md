# Frontend restoration report

## Baseline used

- Restored the complete tracked frontend tree from repository commit `b9283d1` available in the
  uploaded Git history (the frontend lineage merged into the public repository).
- Kept the uploaded, uncommitted backend/services/contracts as the integration target.

## Main changes

- Added generated TypeScript types from `contracts/esb-public-api.yaml`.
- Aligned Identity calls with `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout` and
  `/auth/me`, including refresh cookies and CSRF headers.
- Aligned customer ESB calls with the currently published event, booking, cancellation, trace and
  realtime-ticket operations.
- Preserved the restored customer visual design while replacing unsupported seat-map/reservation and
  list/detail calls with explicit contract-safe states.
- Replaced the old admin CRUD console with a contract-safe console that does not call private
  services or unpublished ESB routes.
- Removed all local private-key files from the export.

## Validation performed

- `python contracts/scripts/validate_contracts.py`: PASS, zero contract errors.
- ESB TypeScript generation: PASS.
- Admin TypeScript check: PASS.
- Customer TypeScript check: PASS after supplying a temporary declaration for `react-router-dom`;
  the uploaded `node_modules` did not contain that dependency, although it is correctly declared in
  `customer-web/package.json` and the lock file.

## Validation not completed in this environment

A clean `npm install`, Vite build and Vitest run could not be completed because the sandbox package
registry did not provide `react-router-dom`/`openapi-typescript`, and the uploaded Windows
`node_modules` contained only Windows Rollup native binaries. Run the normal commands on the target
Windows machine or in CI after `npm install`.
