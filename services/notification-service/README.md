# Notification Service

Canonical contract: `contracts/notification-service.yaml`. The service runs on `8007`. Generic
event ingestion is `POST /webhooks/events` with RFC 3339 timestamp, HMAC and replay protection;
delivery administration uses Service JWT.

Use `docker compose --profile notification up --build --wait`, or migrate separately and start
`uvicorn app.main:create_app --factory --port 8007`.
