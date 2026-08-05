# Seat Inventory Service

Canonical contracts: `contracts/seat-inventory.wsdl` and `contracts/seat-inventory.xsd`. SOAP and
the small admin control plane run on `8003`; callers authenticate with Service JWT.

Use `docker compose --profile seat up --build --wait`, or migrate separately and start
`uvicorn app.main:create_app --factory --port 8003`. Runtime contract paths are
`/app/contracts/seat-inventory.wsdl` and `/app/contracts/seat-inventory.xsd`.
