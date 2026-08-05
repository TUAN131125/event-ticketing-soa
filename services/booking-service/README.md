# Booking Service

Booking Service là nguồn dữ liệu chuẩn cho booking aggregate. Service quản lý vòng
đời booking, kiểm soát chuyển trạng thái, lưu lịch sử, chống thực thi lặp và phát
sự kiện qua transactional outbox.

Service không trực tiếp giữ ghế, thu tiền hoặc phát vé. Booking Orchestrator/ESB
chịu trách nhiệm điều phối Seat Service, Payment Service và Ticket Service, sau đó
gọi các command `confirm`, `fail` hoặc `cancel` tương ứng.

## Vòng đời booking

| Trạng thái hiện tại | Trạng thái kế tiếp | Điều kiện |
| --- | --- | --- |
| `PENDING` | `CONFIRMED` | Có `paymentId` thành công |
| `PENDING` | `FAILED` | Có mã và lý do thất bại |
| `PENDING` | `CANCELLED` | Saga bị hủy trước khi thanh toán hoàn tất |
| `CONFIRMED` | `CANCELLED` | Thanh toán đã có trạng thái `REFUNDED` |
| `FAILED`, `CANCELLED` | Không có | Trạng thái kết thúc |

Mỗi lần chuyển trạng thái cần `expectedVersion`. Giá trị này cung cấp optimistic
concurrency control, ngăn hai bước saga cùng ghi đè một phiên bản booking.

## API nội bộ

Service lắng nghe cổng chuẩn `8004` trong container và trên host.

| Phương thức | Đường dẫn | Công dụng |
| --- | --- | --- |
| `POST` | `/bookings` | Tạo booking ở trạng thái `PENDING` |
| `GET` | `/bookings` | Tìm và phân trang booking |
| `GET` | `/bookings/{bookingId}` | Lấy một booking |
| `POST` | `/bookings/{bookingId}/confirm` | Xác nhận thanh toán thành công |
| `POST` | `/bookings/{bookingId}/fail` | Ghi nhận saga thất bại |
| `POST` | `/bookings/{bookingId}/cancel` | Hủy/hoàn tiền booking |
| `GET` | `/health/live` | Kiểm tra tiến trình |
| `GET` | `/health/ready` | Kiểm tra PostgreSQL và schema |
| `GET` | `/metrics` | Prometheus metrics |

Tất cả endpoint `/bookings` yêu cầu:

- `X-Service-Token`: shared secret nội bộ.
- `X-Caller-Service`: tên service gọi, dùng cho audit.
- `Idempotency-Key`: bắt buộc với mọi command thay đổi dữ liệu.
- `X-Correlation-ID`: không bắt buộc; service tạo mới nếu thiếu hoặc không hợp lệ.
- `X-Actor-ID`: không bắt buộc; định danh người dùng được Orchestrator truyền qua.

Ví dụ tạo booking:

```bash
curl -X POST http://localhost:8004/bookings \
  -H "Content-Type: application/json" \
  -H "X-Service-Token: local-development-token" \
  -H "X-Caller-Service: booking-orchestrator" \
  -H "Idempotency-Key: checkout-7f13-create" \
  -d '{
    "customerId": "CUS-001",
    "eventId": "EV-001",
    "reservationId": "RES-001",
    "paymentMethod": "CARD",
    "items": [
      {"seatId": "A-01", "ticketType": "VIP", "unitPrice": 120.00}
    ],
    "totalAmount": 120.00,
    "currency": "VND"
  }'
```

Swagger UI có tại `http://localhost:8004/docs` trong môi trường local. Có thể tắt
bằng `BOOKING_DOCS_ENABLED=false`; production mặc định tắt.

## Tính nhất quán và chống lặp

Mỗi command chạy trong đúng một PostgreSQL transaction, bao gồm:

1. khóa advisory theo idempotency key;
2. kiểm tra hoặc lưu kết quả replay;
3. khóa booking/reservation cần thay đổi;
4. cập nhật aggregate với `resourceVersion`;
5. thêm bản ghi audit;
6. thêm sự kiện vào outbox.

Gửi lại cùng key và cùng payload trả về kết quả đã hoàn thành mà không tạo thêm
booking, audit hoặc event. Dùng lại key với payload khác trả lỗi
`IDEMPOTENCY_CONFLICT`. Một `reservationId` chỉ có thể thuộc một booking; các yêu
cầu đồng thời được tuần tự hóa bằng PostgreSQL advisory lock và unique constraint.

Idempotency record hết hạn theo `BOOKING_IDEMPOTENCY_TTL_SECONDS`. Dù record đã hết
hạn, unique reservation và logic terminal-command vẫn ngăn tạo/chuyển trạng thái
lặp gây tác dụng phụ.

## Dữ liệu sở hữu

Migration đầu tiên tạo schema PostgreSQL `booking`:

| Bảng | Vai trò |
| --- | --- |
| `bookings` | Booking aggregate và phiên bản hiện tại |
| `booking_items` | Snapshot ghế, loại vé và giá tại lúc đặt |
| `idempotency_records` | Hash yêu cầu và response replay |
| `booking_audit` | Nhật ký bất biến theo caller/correlation/version |
| `outbox_events` | Event ghi nguyên tử cùng thay đổi aggregate |

Outbox sinh `booking.created`, `booking.confirmed`, `booking.failed` và
`booking.cancelled`. Một relay riêng của hạ tầng phải đọc các dòng có
`published_at IS NULL`, publish at-least-once rồi đánh dấu kết quả. Consumer cần
deduplicate bằng `event_id`; Booking Service không đánh dấu published trước khi
broker xác nhận.

## Chạy local

Yêu cầu Docker Compose:

```bash
docker compose --profile booking up --build --wait
```

Root Compose chạy `booking-migrate` trước khi khởi động API. Cấu hình local nằm
trong root `.env.example`.

Chạy trực tiếp bằng Python 3.12:

```powershell
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt
$env:BOOKING_DATABASE_URL = "postgresql+psycopg://booking:booking@localhost:5437/booking"
$env:BOOKING_SERVICE_TOKEN = "local-development-token"
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8004
```

Ứng dụng đọc biến môi trường của tiến trình. `.env.example` liệt kê toàn bộ cấu
hình được hỗ trợ.

## Kiểm định

```bash
python -m ruff format --check app migrations tests
python -m ruff check app migrations tests
python -m mypy app
python -m pytest -m "not integration"
```

Integration và concurrency test cần PostgreSQL thật:

```powershell
docker compose --profile booking up -d --wait
$env:BOOKING_TEST_DATABASE_URL = "postgresql+psycopg://booking:booking@localhost:55434/booking_test"
python -m pytest -m integration
```

Các integration test kiểm tra migration, lifecycle đầy đủ, audit/outbox nguyên tử,
idempotency conflict, reservation conflict và nhiều yêu cầu tạo đồng thời.

## Vận hành

- Readiness trả `503` nếu PostgreSQL/schema chưa sẵn sàng hoặc tiến trình đang
  draining.
- Log JSON chỉ chứa metadata có giới hạn; không ghi body hoặc service token.
- Metrics chỉ dùng nhãn có cardinality thấp cho HTTP, command, replay, trạng thái
  booking và readiness.
- Lock timeout, statement timeout, pool size và thời hạn idempotency đều cấu hình
  qua biến môi trường trong `.env.example`.
- Lỗi API có mã ổn định, `correlationId`, cờ `retryable` và không làm lộ exception
  hoặc thông tin kết nối.
