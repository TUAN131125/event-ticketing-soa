# Ticket Service

Ticket Service là nguồn dữ liệu authoritative cho vé điện tử sau khi booking đã
được xác nhận thanh toán. Mỗi ghế tương ứng đúng một `Ticket`; toàn bộ vé của một
booking được phát hành atomically trong một transaction để không xuất hiện trạng
thái phát hành nửa chừng.

## Vòng đời vé

```mermaid
stateDiagram-v2
    [*] --> VALID: issue
    VALID --> VALID: regenerate QR
    VALID --> CHECKED_IN: valid QR + authorized staff
    VALID --> CANCELLED: booking cancellation/refund
```

`CHECKED_IN` và `CANCELLED` là trạng thái cuối. Vé đã check-in không thể hủy; vé đã
hủy không thể check-in hoặc tạo QR mới. Mọi mutation dùng `expectedVersion` để
phát hiện cập nhật đồng thời.

## Thiết kế QR an toàn

Database chỉ lưu `qrVersion`, không lưu QR image, raw token hoặc signing key.
Service tạo token dạng:

```text
TKT1.<ticketId>.<qrVersion>.<HMAC-SHA256 signature>
```

Ảnh QR SVG data URI được dựng khi trả ticket detail. `regenerateTicketQr` tăng cả
`qrVersion` và `resourceVersion`, khiến QR cũ không còn hợp lệ ngay lập tức.
Check-in kiểm tra đồng thời chữ ký, `ticketId`, phiên bản QR và trạng thái ticket.
QR token không được ghi vào audit, outbox hoặc log.

`TICKET_QR_SIGNING_KEY` phải nằm trong secret manager. Việc đổi key trực tiếp sẽ
làm mất hiệu lực toàn bộ QR hiện tại; production cần quy trình rotate có kiểm soát.

## API nội bộ

Tất cả endpoint nghiệp vụ yêu cầu `X-Service-Token` và `X-Caller-Service`.
Command yêu cầu thêm `Idempotency-Key`. Các header audit tùy chọn là
`X-Correlation-ID`, `X-Actor-ID` và `X-Actor-Roles`.

| Method | Endpoint | Mục đích |
|---|---|---|
| `POST` | `/tickets/issue` | Phát hành atomically một vé cho mỗi ghế booking |
| `GET` | `/tickets` | Lọc/phân trang ticket summary, không nhúng QR image |
| `GET` | `/tickets/{ticketId}` | Đọc ticket và QR hiện tại nếu còn `VALID` |
| `POST` | `/tickets/{ticketId}/cancel` | Hủy vé chưa sử dụng |
| `POST` | `/tickets/{ticketId}/check-in` | Xác minh QR và check-in atomically |
| `POST` | `/tickets/{ticketId}/qr/regenerate` | Rotate QR, vô hiệu QR cũ |

Check-in bắt buộc có `X-Actor-ID` và một trong hai role `CHECKIN_STAFF`, `ADMIN`.
Gateway tin cậy phải xác minh access token, loại bỏ mọi `X-Actor-*` do client tự
gửi rồi mới thêm actor context nội bộ.

Hợp đồng đầy đủ:
[`contracts/ticket-service.yaml`](../../contracts/ticket-service.yaml).

## Phát hành từ Booking Orchestrator

Sau `booking.confirmed`, Orchestrator đọc snapshot booking authoritative rồi gọi
`issueTickets` với `bookingId`, `customerId`, `eventId`, `paymentId` và danh sách
`seatId`, `seatLabel`, `ticketType`.

```mermaid
sequenceDiagram
    participant B as Booking Orchestrator
    participant T as Ticket Service
    participant O as Outbox Relay
    B->>T: issueTickets(confirmed booking snapshot)
    T->>T: lock booking + all event seats
    T->>T: insert all tickets, audits and outbox rows
    T-->>B: complete ticket set + QR images
    O->>T: read unpublished outbox rows
    O-->>B: publish ticket.issued per ticket
```

Service không join hoặc đọc database của Booking, Payment hay Event Service. Unique
constraint `(bookingId, seatId)` và partial unique index `(eventId, seatId)` cho vé
chưa hủy, cùng advisory lock theo booking/ghế, ngăn phát hành trùng ngay cả khi có
request đồng thời. Sau khi ticket `CANCELLED`, ghế có thể được phát hành cho booking
mới nhưng ticket cũ vẫn được giữ làm lịch sử.

## Idempotency, audit và sự kiện

- Idempotency key được khóa bằng PostgreSQL advisory lock và gắn với hash canonical
  của request.
- Dùng lại cùng key/payload xác nhận kết quả đã hoàn tất rồi hydrate trạng thái
  Ticket hiện tại trước khi dựng QR; vì vậy replay không bao giờ trả QR version đã
  bị rotate. Dùng payload khác trả `IDEMPOTENCY_CONFLICT`.
- Retry phát hành bằng key mới vẫn trả đúng ticket set nếu định nghĩa booking trùng
  hoàn toàn.
- Mỗi thay đổi tạo audit row và outbox row trong cùng transaction.

Các event:

- `ticket.issued`
- `ticket.checked-in`
- `ticket.cancelled`
- `ticket.qr-regenerated`

JSON Schema nằm trong [`contracts/event-messages.schema.json`](../../contracts/event-messages.schema.json). Broker relay là
adapter riêng, publish các row `published_at IS NULL`; consumer deduplicate theo
`eventId`.

## Database

Migration tạo schema `ticket`:

- `tickets`: snapshot aggregate và trạng thái check-in/cancellation;
- `idempotency_records`: response snapshot có TTL;
- `ticket_audit`: caller, actor, correlation, version và transition;
- `outbox_events`: event chờ publish, số lần thử và lỗi cuối.

DB constraint kiểm tra state consistency: `CHECKED_IN` phải có thời gian/gate/actor;
`CANCELLED` phải có thời gian/lý do; `VALID` không được mang dữ liệu terminal.

## Chạy local

```powershell
Copy-Item ..\..\.env.example ..\..\.env
docker compose --profile ticket up --build --wait
```

Service: `http://localhost:8006`; PostgreSQL không được publish ra host.

Chạy trực tiếp:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:TICKET_DATABASE_URL='postgresql+psycopg://ticket:ticket@localhost:5439/ticket'
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\uvicorn.exe app.main:app --port 8006
```

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit tests\contract tests\security
```

Integration/concurrency test:

```powershell
docker compose --profile ticket up -d --wait
$env:TICKET_TEST_DATABASE_URL='postgresql+psycopg://ticket:ticket@localhost:55436/ticket_test'
.\.venv\Scripts\python.exe -m pytest
```

Kiểm tra chất lượng:

```powershell
.\.venv\Scripts\python.exe -m ruff format --check app tests
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
```

## Production checklist

- `TICKET_APP_ENV=production`.
- `TICKET_SERVICE_TOKEN` và `TICKET_QR_SIGNING_KEY` là hai secret độc lập, ngẫu
  nhiên, tối thiểu 32 ký tự.
- Gateway xác minh identity/role và xóa actor header không tin cậy từ internet.
- Dùng TLS/mTLS giữa service; không log body, QR token hoặc QR data URI.
- Tắt docs bằng `TICKET_DOCS_ENABLED=false`.
- Alert double check-in, QR invalid tăng đột biến, lock timeout và outbox tồn lâu.
- Consumer dùng at-least-once delivery phải deduplicate theo `eventId`.
