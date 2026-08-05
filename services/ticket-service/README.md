# Ticket Service

Canonical contract: `contracts/ticket-service.yaml`. The service runs on `8006`; issuance is
`POST /tickets:issue`, QR reissue is `POST /tickets/{ticketId}/reissue-qr`, and internal calls use
Service JWT.

Use `docker compose --profile ticket up --build --wait`, or migrate separately and start
`uvicorn app.main:create_app --factory --port 8006`.
