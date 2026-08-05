# Event Service

Canonical contract: `contracts/event-service.yaml`. The service runs on `8002`; command routes are
`publish`, `pause` and `cancel`, with no legacy sales aliases. Internal calls require Service JWT.

Use `docker compose --profile event up --build --wait`, or migrate separately and start
`uvicorn app.main:create_app --factory --port 8002`. Health probes are `/health/live` and
`/health/ready`.
