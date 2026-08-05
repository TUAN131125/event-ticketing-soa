# Seat Inventory Service

Seat Inventory là service T0 quản lý sơ đồ ghế, giữ ghế có thời hạn và xác
nhận hoặc giải phóng ghế. PostgreSQL là nguồn dữ liệu có thẩm quyền duy nhất.
Service không dùng khóa in-memory hay Redis để quyết định tính toàn vẹn.

## Kiến trúc và nguyên tắc

```text
SOAP / Admin HTTP
        |
        v
Transport validation + service authentication
        |
        v
Application command/query handlers
        |
        v
SQLAlchemy transaction (READ COMMITTED)
        |
        v
PostgreSQL row/advisory locks + constraints + audit
```

- `GetSeatMap` và `CheckAvailability` chỉ trả snapshot. `ReserveSeats` luôn
  kiểm tra lại trạng thái trong transaction.
- `ReserveSeats` khóa các row ghế bằng `SELECT ... FOR UPDATE`, theo thứ tự
  `seatId` tăng dần.
- `ReserveSeats`, `ExtendReservation`, `ConfirmSeats` và `ReleaseSeats` dùng
  idempotency key. Khóa advisory theo key, business state, audit và kết quả
  replay đều commit cùng transaction.
- TTL dùng `clock_timestamp()` của PostgreSQL. Worker expiry chạy an toàn trên
  nhiều replica bằng `FOR UPDATE SKIP LOCKED`.
- Mọi thay đổi ghế ghi `seat.seat_audit` trong cùng transaction.
- Service fail closed khi database, reservation owner hoặc trạng thái ghế
  không xác định.

State machine:

```text
Seat:        AVAILABLE -> HELD -> SOLD
                         HELD -> AVAILABLE (release/expire)

Reservation: ACTIVE -> CONFIRMED
             ACTIVE -> RELEASED
             ACTIVE -> EXPIRED
```

## Contract

WSDL 1.1 document/literal canonical: [`../../contracts/seat-inventory.wsdl`](../../contracts/seat-inventory.wsdl).

| Operation | Loại | Ghi chú |
|---|---|---|
| `GetSeatMap` | Query | Snapshot sơ đồ ghế |
| `CheckAvailability` | Query | Snapshot trạng thái ghế yêu cầu |
| `ReserveSeats` | Command | Atomic hold, bắt buộc idempotency |
| `GetReservation` | Query | Reservation authoritative |
| `ExtendReservation` | Command | Version check, giới hạn số lần |
| `ConfirmSeats` | Command | `HELD -> SOLD`, fail nếu hết TTL |
| `ReleaseSeats` | Command | Chỉ release ghế HELD thuộc reservation |
| `ExpireReservations` | Command/worker | Batch expiry dùng `SKIP LOCKED` |

SOAP Fault có `code`, `message`, `correlationId`, `retryable`; response không
chứa traceback, SQL, DSN, secret hoặc hostname nội bộ.

`ConfigureInventory` không nằm trong WSDL v1.0 nên được triển khai tại
`POST /admin/inventory`. Endpoint này dùng cùng service token và chỉ cho phép
cấu hình ghế `AVAILABLE`/`BLOCKED`; không cho xóa hoặc thay đổi ghế `HELD` hay
`SOLD`. `AuditSeatChange` là hành vi nội bộ, không phải public operation.

## Chạy bằng Docker

Yêu cầu Docker Desktop hoặc Docker Engine:

```powershell
docker compose --profile seat up --build -d --wait
```

Trên PowerShell, có thể seed bằng:

```powershell
Get-Content -Raw database/seed.sql |
  docker compose exec -T postgres psql -U seat_inventory -d seat_inventory
```

Các endpoint:

```text
SOAP:       http://localhost:8003/soap
WSDL:       http://localhost:8003/soap?wsdl
Admin docs: http://localhost:8003/admin/docs
Liveness:   http://localhost:8003/health/live
Readiness:  http://localhost:8003/health/ready
Metrics:    http://localhost:8003/metrics
```

Root Compose chạy `seat-migrate` trước khi khởi động Uvicorn. Service dùng cổng
chuẩn `8003` cả trong container lẫn trên host.

## Chạy trực tiếp bằng Python

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:SEAT_DATABASE_URL = "postgresql+psycopg://seat_inventory:seat_inventory@localhost:5433/seat_inventory"
$env:SEAT_SERVICE_TOKEN = "local-development-token"
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8003
```

## Cấu hình inventory

Sau khi service chạy:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8003/admin/inventory `
  -Headers @{
    "X-Service-Token" = "local-development-token"
    "X-Correlation-ID" = "COR-CONFIG-1"
    "X-Actor-ID" = "ADMIN-1"
  } `
  -ContentType "application/json" `
  -InFile contracts/examples/configure-inventory.json
```

`inventoryVersion` phải tăng. Lần cấu hình đầu tiên dùng version `1`.

## Gọi SOAP

Mỗi operation có request mẫu trong `contracts/examples`. Ví dụ:

```powershell
Invoke-WebRequest `
  -Method Post `
  -Uri http://localhost:8003/soap `
  -Headers @{
    "X-Service-Token" = "local-development-token"
    "SOAPAction" = "ReserveSeats"
  } `
  -ContentType "text/xml; charset=utf-8" `
  -InFile contracts/examples/reserve-seats-request.xml
```

Zeep client có thể gọi từng operation hoặc chạy workflow bao phủ đủ 8
operations:

```powershell
.\.venv\Scripts\python.exe scripts/zeep_client.py workflow
.\.venv\Scripts\python.exe scripts/zeep_client.py GetSeatMap
.\.venv\Scripts\python.exe scripts/zeep_client.py GetReservation --reservation-id <ID>
```

Workflow lần lượt gọi `GetSeatMap`, `CheckAvailability`, `ReserveSeats`,
`GetReservation`, `ExtendReservation`, `ReleaseSeats`, một lần reserve khác,
`ConfirmSeats` và `ExpireReservations`.

## Migration và seed

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\alembic.exe downgrade base
Get-Content -Raw database/seed.sql |
  docker compose exec -T postgres psql -U seat_inventory -d seat_inventory
```

Migration tạo schema `seat`, foreign key nội bộ, check constraint cho state,
unique booking reservation, index expiry/status, audit và idempotency.

## Kiểm thử

Không dùng SQLite cho integration/concurrency test.

```powershell
docker compose --profile seat up -d --wait
$env:SEAT_TEST_DATABASE_URL = "postgresql+psycopg://seat_inventory:seat_inventory@localhost:55432/seat_inventory_test"
.\.venv\Scripts\python.exe -m ruff format --check app migrations scripts tests
.\.venv\Scripts\python.exe -m ruff check app migrations scripts tests
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m pytest
```

Test suite bao phủ contract WSDL/XSD, XML sai schema, DTD/XXE, payload limit,
idempotency replay/conflict, multi-seat rollback, confirm hết TTL, lock
timeout, deadlock thật, hai expiry worker, rollback giữa transaction và 100
request đồng thời cùng một ghế.

## Graceful shutdown và vận hành

Liveness chỉ kiểm tra process. Readiness kiểm tra kết nối database và Alembic
version; trong drain mode trả `503`. Khi nhận shutdown, service ngừng worker,
chờ request/transaction do Uvicorn quản lý và dispose connection pool. Log là
JSON có correlation ID nhưng không ghi SOAP body hoặc token. Metrics chính:

```text
seat_operation_total
seat_operation_duration_seconds
seat_soap_fault_total
seat_reserve_conflict_total
seat_expired_reservations_total
seat_expiry_worker_up
seat_readiness
```

## Các điểm đã chốt khi tài liệu chưa đồng nhất

- Tài liệu nghiệp vụ liệt kê 10 action nhưng WSDL chỉ có 8 operation:
  `ConfigureInventory` là admin REST; `AuditSeatChange` là hành vi transaction
  nội bộ.
- Enum authoritative là `AVAILABLE`, `HELD`, `SOLD`, `BLOCKED`; từ
  `RESERVED` trong mô tả cũ được chuẩn hóa thành `HELD`.
- `ExpireReservations` vừa được công bố trong WSDL để giữ đủ contract, vừa có
  worker nội bộ. Cả hai dùng chung application handler.
- Port chuẩn của Seat Inventory là `8003`.
- `expectedVersion` là bắt buộc cho `ExtendReservation` và `ConfirmSeats` để
  tránh cập nhật trên state đã thay đổi.
