# Payment Service

Canonical contract: `contracts/payment-service.yaml`. The service runs on `8005`; internal calls
use Service JWT and provider callbacks use timestamped HMAC. Money uses `amountMinor` and
`currency`.

Use `docker compose --profile payment up --build --wait`, or migrate separately and start
`uvicorn app.main:create_app --factory --port 8005`.
