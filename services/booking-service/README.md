# Booking Service

Canonical contract: `contracts/booking-service.yaml`. The service runs on `8004`, validates
Service JWTs, uses `Idempotency-Key` and `If-Match`, and owns authoritative booking access
decisions.

Use `docker compose --profile booking up --build --wait`, or run migrations separately and start
`uvicorn app.main:create_app --factory --port 8004`. Readiness is `/health/ready`.
