# Payment Service

Payment Service là sổ cái thanh toán nội bộ, độc lập với nhà cung cấp. Service quản
lý duy nhất một `Payment` cho mỗi booking, lưu lịch sử refund bất biến, audit mọi
thay đổi và ghi domain event vào transactional outbox trong cùng transaction.

## Ranh giới bảo mật

API này **không nhận và không lưu PAN, CVV, ngày hết hạn hoặc dữ liệu thẻ thô**.
`paymentMethod` chỉ là mã loại phương thức không nhạy cảm như `CARD_TOKEN` hoặc
`BANK_TRANSFER`, không phải token/credential thực tế;
`providerReference` và `providerRefundReference` là mã giao dịch do nhà cung cấp
trả về.

Provider adapter hoặc Payment Orchestrator chịu trách nhiệm:

1. giao tiếp với cổng thanh toán bằng credential nằm trong secret manager;
2. xác minh chữ ký webhook và đối chiếu merchant/account, số tiền, currency;
3. chỉ gửi kết quả đã xác minh vào các command của Payment Service;
4. dùng một `Idempotency-Key` ổn định cho mỗi thao tác nghiệp vụ.

Payment Service không giả lập việc charge tiền và không coi payload trực tiếp từ
trình duyệt hay webhook chưa xác minh là kết quả đáng tin cậy.

## Vòng đời aggregate

```mermaid
stateDiagram-v2
    [*] --> PENDING: create
    PENDING --> AUTHORIZED: provider approved
    PENDING --> FAILED: provider declined
    PENDING --> CANCELLED: cancel
    PENDING --> CAPTURED: verified reconciliation only
    AUTHORIZED --> CAPTURED: capture succeeded
    AUTHORIZED --> FAILED: capture failed
    AUTHORIZED --> CANCELLED: void/cancel
    CAPTURED --> PARTIALLY_REFUNDED: partial refund
    CAPTURED --> REFUNDED: full refund
    PARTIALLY_REFUNDED --> PARTIALLY_REFUNDED: another partial refund
    PARTIALLY_REFUNDED --> REFUNDED: remaining amount refunded
```

`FAILED`, `CANCELLED` và `REFUNDED` là trạng thái cuối. Mỗi mutation yêu cầu
`expectedVersion`; trạng thái không được lùi và tổng refund không thể vượt quá số
tiền đã capture.

## API nội bộ

Mọi endpoint nghiệp vụ yêu cầu:

- `X-Service-Token`: shared secret nội bộ;
- `X-Caller-Service`: tên service gọi để audit;
- `X-Correlation-ID`: tùy chọn, service sẽ sinh nếu thiếu;
- `X-Actor-ID`: tùy chọn;
- `Idempotency-Key`: bắt buộc với mọi command.

| Method | Endpoint | Mục đích |
|---|---|---|
| `POST` | `/payments` | Tạo payment `PENDING`; một payment cho mỗi booking |
| `GET` | `/payments` | Lọc và phân trang payment |
| `GET` | `/payments/{paymentId}` | Đọc payment hiện tại |
| `GET` | `/payments/{paymentId}/refunds` | Đọc refund ledger |
| `POST` | `/payments/{paymentId}/authorize` | Ghi authorization/decline đã xác minh |
| `POST` | `/payments/{paymentId}/capture` | Ghi capture thành công/thất bại đã xác minh |
| `POST` | `/payments/{paymentId}/cancel` | Hủy trước capture |
| `POST` | `/payments/{paymentId}/refund` | Ghi full/partial refund đã hoàn tất ở provider |
| `POST` | `/payments/{paymentId}/reconcile` | Đồng bộ kết quả provider mà không cho state regression |

Hợp đồng đầy đủ nằm tại
[`contracts/openapi/payment-service.yaml`](../../contracts/openapi/payment-service.yaml).
Swagger UI được mở ở `/docs` ngoài production.

## Tính nhất quán và khả năng retry

- PostgreSQL advisory lock tuần tự hóa cùng một idempotency key và cùng một
  `bookingId`.
- `payment.payments.booking_id` là unique, nên hai request đồng thời không thể tạo
  hai payment cho một booking.
- Idempotency record lưu hash canonical của request và snapshot response. Dùng lại
  key với payload khác trả `IDEMPOTENCY_CONFLICT`.
- `provider + providerReference` và `provider + providerRefundReference` là unique,
  ngăn một giao dịch provider bị gắn cho hai aggregate.
- Retry cùng kết quả cuối bằng key mới vẫn an toàn nếu outcome trùng khớp; outcome
  khác bị từ chối.
- Row lock, optimistic `resourceVersion`, lock timeout, statement timeout và retry
  có giới hạn bảo vệ service trước race condition và sự cố DB ngắn hạn.

## Dữ liệu và sự kiện

Migration đầu tiên tạo schema `payment` với các bảng:

- `payments`: snapshot authoritative của aggregate;
- `refunds`: ledger từng khoản refund, gồm `REQUESTED` và `RECONCILIATION`;
- `idempotency_records`: kết quả command có TTL;
- `payment_audit`: caller, actor, correlation, version và status transition;
- `outbox_events`: event chưa/đã publish và số lần publish lỗi.

Các event được ghi atomically với thay đổi aggregate:

- `payment.created`
- `payment.authorized`
- `payment.succeeded`
- `payment.failed`
- `payment.cancelled`
- `payment.refunded` (cả partial và full)

JSON Schema nằm trong [`contracts/events`](../../contracts/events). Broker relay là
thành phần triển khai riêng: đọc các row `published_at IS NULL`, publish envelope,
rồi cập nhật trạng thái gửi. Nhờ vậy code lõi không bị khóa vào Kafka/RabbitMQ cụ
thể.

## Luồng phối hợp khuyến nghị

```mermaid
sequenceDiagram
    participant O as Payment Orchestrator
    participant A as Provider Adapter
    participant P as Payment Service
    participant B as Booking Service
    O->>P: createPayment
    O->>A: authorize/capture with provider token
    A-->>O: verified provider outcome
    O->>P: authorizePayment / capturePayment
    P-->>O: CAPTURED + payment.succeeded
    O->>B: confirmBooking(paymentId)
```

Khi payment thất bại, Orchestrator đánh dấu booking failed và giải phóng reservation.
Khi hủy booking đã thanh toán, refund phải hoàn tất ở provider và Payment Service
phải đạt `REFUNDED` trước khi Booking Service nhận lệnh cancel.

## Chạy local

Yêu cầu Docker hoặc Python 3.12 và PostgreSQL 16.

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Service: `http://localhost:8005`; PostgreSQL: `localhost:5438`.
Container chạy `alembic upgrade head` trước khi nhận traffic.

Chạy trực tiếp:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:PAYMENT_DATABASE_URL='postgresql+psycopg://payment:payment@localhost:5438/payment'
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\uvicorn.exe app.main:app --port 8005
```

## Kiểm thử

Unit, contract và security test không cần database:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit tests\contract tests\security
```

Integration/concurrency test dùng PostgreSQL test riêng:

```powershell
docker compose -f docker-compose.test.yml up -d
$env:PAYMENT_TEST_DATABASE_URL='postgresql+psycopg://payment:payment@localhost:55435/payment_test'
.\.venv\Scripts\python.exe -m pytest
```

Kiểm tra chất lượng:

```powershell
.\.venv\Scripts\python.exe -m ruff format --check app tests
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
```

## Production checklist

- Đặt `PAYMENT_APP_ENV=production` và `PAYMENT_SERVICE_TOKEN` ngẫu nhiên tối thiểu
  32 ký tự; không dùng giá trị local.
- Tắt docs bằng `PAYMENT_DOCS_ENABLED=false`.
- Dùng TLS/mTLS giữa các service và secret manager cho token/credential provider.
- Chạy outbox relay với at-least-once delivery; consumer phải deduplicate bằng
  `eventId`.
- Cảnh báo theo readiness, lỗi provider, lock timeout, idempotency conflict,
  `publish_attempts` và outbox chưa publish quá lâu.
- Đối soát provider định kỳ qua command `reconcile`; không sửa DB trực tiếp.
