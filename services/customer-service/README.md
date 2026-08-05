# Customer Service

Canonical contract: `contracts/customer-service.yaml`. The service runs on `8001`, requires a
Service JWT on business/internal routes, and exposes `/health/live` and `/health/ready`.

Use `docker compose --profile customer up --build --wait`, or run `customer-migrate` separately
then `uvicorn app.main:create_app --factory --port 8001`. Configuration comes from the root
`.env.example`; no service-local contract or credential is maintained.
