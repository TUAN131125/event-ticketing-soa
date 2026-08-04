# Event Service

Event Service quản lý vòng đời sự kiện: tạo, xem chi tiết, liệt kê (lọc +
phân trang), thay thế toàn bộ profile, mở bán/tạm dừng/hủy, và kiểm tra
điều kiện được phép bán vé (sale-eligibility) cho ESB gọi trước khi
booking. Đây là service T2 (theo phân loại DOC-04): không có tài nguyên
tranh chấp đồng thời như Seat Inventory, nhưng có `resourceVersion`/
`If-Match` để tránh lost-update khi 2 admin sửa cùng lúc.

**Bản này viết lại để khớp đúng `contracts/openapi/event-service.yaml`
(Giai đoạn 5) và đặc tả `01_EVENT_SERVICE.docx` (Giai đoạn 3)** — thay
cho bản MVP trước chỉ có CRUD lõi, sai path (`/open-sales` thay vì
`/publish`), thiếu `resourceVersion`, thiếu `Idempotency-Key`, thiếu
audit, và dùng error envelope không khớp contract.

## Endpoint (khớp OpenAPI Giai đoạn 5)

| Method | Path | Header bắt buộc | Ghi chú |
|---|---|---|---|
| GET | `/health/live`, `/health/ready` | | |
| GET | `/events?status=&page=&pageSize=` | | EVT-03, tổng số trả qua `X-Total-Count` |
| POST | `/events` | `Idempotency-Key` | EVT-01, tạo DRAFT, trả 201 |
| GET | `/events/{id}` | | EVT-04, 404 nếu không có |
| PUT | `/events/{id}` | `Idempotency-Key`, `If-Match` | EVT-02, replace toàn bộ profile |
| POST | `/events/{id}/publish` | `Idempotency-Key`, `If-Match` | EVT-07, DRAFT/PAUSED → ON_SALE |
| POST | `/events/{id}/pause` | `Idempotency-Key`, `If-Match` | EVT-08, ON_SALE → PAUSED |
| POST | `/events/{id}/cancel` | `Idempotency-Key`, `If-Match` | EVT-09, → CANCELLED |
| GET | `/events/{id}/sale-eligibility` | | EVT-10, ESB gọi trước booking |

`If-Match` gửi dạng `"3"` (đúng resourceVersion hiện tại của bản ghi,
lấy từ response trước đó) — sai sẽ trả **409 VERSION_CONFLICT**.
`Idempotency-Key` là chuỗi tuỳ ý do client sinh; gọi lại với cùng key +
cùng thân request sẽ trả lại đúng response đã lưu (không chạy lại
nghiệp vụ); cùng key nhưng khác thân request → **409
IDEMPOTENCY_KEY_REUSED**.

## Lỗi trả về

Theo đúng `ErrorResponse` trong contract:

```json
{
  "correlationId": "...",
  "traceId": null,
  "error": { "code": "EVENT_NOT_FOUND", "message": "...", "retryable": false, "details": null }
}
```

Mã lỗi: `EVENT_NOT_FOUND` (404), `INVALID_EVENT_TRANSITION` (409),
`VERSION_CONFLICT` (409), `INVALID_EVENT_DATA` (422),
`IDEMPOTENCY_KEY_REUSED` (409).

## Dữ liệu (schema `event`, quản lý bằng Alembic)

- `events`: `id` (EVxxx, sinh từ `SEQUENCE`), `name`, `venue`, `starts_at`,
  `sale_starts_at`, `sale_ends_at`, `status`
  (`DRAFT`/`ON_SALE`/`PAUSED`/`CANCELLED`/`ENDED`), `resource_version`,
  `created_at`.
- `ticket_types` (bảng con, `ON DELETE CASCADE`): `code`, `name`,
  `amount_minor`, `currency` (Money — không còn là số nguyên đơn giản).
- `event_audit` (EVT-11, append-only): ghi mọi mutation (`actor_id`,
  `action`, `changed_at`). Chưa có endpoint đọc audit qua REST (không có
  trong contract) — đọc trực tiếp qua DB hoặc `AuditRepository.list_for_event`
  nếu cần cho demo.
- `idempotency_keys`: lưu response đã xử lý theo từng `Idempotency-Key`.

Seed sẵn `EV001` (`ON_SALE`, 2 loại vé VIP/STANDARD) để tương thích
Postman/test cũ.

## Giới hạn đã biết (ghi rõ để không hiểu nhầm là "xong 100%")

- **`ENDED`** có trong enum status nhưng **không có endpoint mutation
  nào đạt tới trạng thái này** trong OpenAPI baseline hiện tại (chỉ có
  publish/pause/cancel) — cần một cơ chế tự động (job theo `saleEndsAt`)
  nếu muốn dùng, chưa làm.
- **Auth**: `X-Actor-Id` là header tuỳ chọn, dùng để ghi audit — CHƯA có
  JWT/service-to-service auth thật (giống toàn bộ MVP hiện tại của
  nhóm, xem `middleware/authentication.py` các service khác).
- **EVT-05/06 (tạo/sửa/ẩn loại vé + giá theo thời gian hiệu lực riêng)**:
  OpenAPI baseline hiện tại không có endpoint riêng cho việc này —
  `ticketTypes` chỉ được set trọn gói qua `POST /events` hoặc
  `PUT /events/{id}` (replace toàn bộ). Nếu nhóm cần endpoint riêng,
  đây là việc bổ sung contract trước, không phải lỗi thiếu code.

## Chạy thử

```powershell
cd services\event-service
docker compose up --build
```

```powershell
curl.exe http://localhost:8002/events/EV001
curl.exe -X POST http://localhost:8002/events -H "Content-Type: application/json" -H "Idempotency-Key: demo-1" -d "{\"name\":\"Hoi thao AI\",\"venue\":\"Trung tam hoi nghi\",\"startsAt\":\"2026-09-15T09:00:00+07:00\",\"saleStartsAt\":\"2026-08-05T00:00:00+07:00\",\"saleEndsAt\":\"2026-09-14T00:00:00+07:00\",\"ticketTypes\":[{\"code\":\"STD\",\"name\":\"Standard\",\"price\":{\"amountMinor\":100000,\"currency\":\"VND\"}}]}"
curl.exe -X POST http://localhost:8002/events/EV001/pause -H "Idempotency-Key: demo-2" -H "If-Match: \"1\""
```

## Test

```powershell
pip install -r requirements-dev.txt
pytest tests/unit                          # 11 test, khong can Postgres
pytest tests/integration -m integration    # 10 test, can Postgres that
ruff check app/
mypy app/    # con vai loi khong-nghiem-trong tu Column[] typing cua SQLAlchemy declarative (chung toan bo repo)
```

Đã chạy kiểm chứng trước khi đóng gói: **21/21 test pass**, `ruff check`
sạch, server thật chạy được, và test bằng curl trực tiếp toàn bộ luồng
publish → version-conflict → sale-eligibility → pause → cancel →
idempotency replay/conflict.
