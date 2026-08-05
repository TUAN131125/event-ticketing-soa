# Realtime Status Service

Canonical contracts: `contracts/realtime-service.openapi.yaml` and
`contracts/realtime-service.asyncapi.yaml`. HTTP runs on `8008`; internal status ingestion uses
Service JWT. Browsers authenticate within five seconds using the ESB-issued one-time WebSocket
ticket in an `authenticate` frame. Access tokens in headers, subprotocols or query strings are
rejected.

Use `docker compose --profile realtime up --build --wait`, or start
`uvicorn app.main:create_app --factory --port 8008` after mounting the configured public keys.
