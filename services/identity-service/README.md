# Identity Service

Canonical contract: `contracts/identity-service.yaml`. Identity runs on `8009` and exposes User
JWT/JWKS endpoints plus `/health/live` and `/health/ready`.

The container requires RSA keys through mounted file paths or Base64 environment values. Its
entrypoint materializes key bytes under `/tmp/identity-signing` and fails closed when key material
is absent or ambiguous; it never generates keys or runs Alembic.

Use `docker compose --profile identity up --build --wait`. For direct execution, run the migration
explicitly and then start `uvicorn app.main:create_app --factory --port 8009` with
`IDENTITY_OPENAPI_PATH` pointing at the canonical built contract.
