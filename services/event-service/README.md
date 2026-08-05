# Event Service

Event Service quản lý vòng đời sự kiện (tạo, cập nhật thông tin, và máy
trạng thái bán vé DRAFT → ON_SALE → PAUSED/CLOSED, hoặc → CANCELLED). Đây
là service T2 (theo phân loại DOC-04 của nhóm): không có tài nguyên tranh
chấp đồng thời như Seat Inventory, nên service ưu tiên sự đơn giản và rõ
ràng của REST + PostgreSQL thay vì các cơ chế khóa nâng cao.

## Kiến trúc

Clean Architecture / layered, cùng phong cách với các service khác trong
repo (Customer Service, Seat Inventory Service, Identity Service):

```text
HTTP (FastAPI)
    |
    v
app/api            - nhan request, tra response (khong chua logic)
    |
    v
app/application     - use case (create/get/update event, open/pause/close
    |                 sales, cancel)
    v
app/domain          - entity + state machine (rules.py), khong biet
    |                 FastAPI/DB
    v
app/repositories     - interface (Protocol) EventRepository
    |
    v
app/infrastructure/database - PostgresEventRepository (SQLAlchemy 2.0)
    |
    v
PostgreSQL (schema "event")
```

Domain và application layer chỉ phụ thuộc vào `EventRepository`
(Protocol) - không biết dữ liệu lưu ở đâu. Nhờ vậy khi nâng cấp từ
`InMemoryEventRepository` (bản MVP ban đầu) lên `PostgresEventRepository`
thật, không phải sửa gì ở tầng `application`/`api`, chỉ đổi 1 dòng trong
`app/dependencies.py`.

`InMemoryEventRepository` vẫn còn trong code nhưng chỉ dùng cho
`tests/unit` (chạy nhanh, không cần Postgres) - app thật (`app/main.py`)
luôn dùng `PostgresEventRepository`.

## Dữ liệu

- Schema riêng `event` trong PostgreSQL, quản lý bằng Alembic
  (`migrations/versions/0001_initial_schema.py`).
- Bảng `event.events`: `id` (dạng `EV001`, `EV002`, ...), `name`,
  `location`, `start_time`, `status`
  (`DRAFT`/`ON_SALE`/`PAUSED`/`CLOSED`/`CANCELLED`), `created_at`.
- Bảng `event.ticket_types` (bảng con, `ON DELETE CASCADE` theo
  `event_id`): `id`, `event_id`, `type`, `price`. Được ghi cùng lúc với
  `events` khi tạo sự kiện; không có use case nào sửa `ticket_types` sau
  khi tạo, nên `update()` chỉ đụng tới cột của `events`.
- `id` được sinh bằng PostgreSQL `SEQUENCE event.event_id_seq` - sinh tại
  tầng database nên vẫn đúng khi chạy nhiều worker/container cùng lúc
  (khác với biến đếm trong bộ nhớ của bản MVP cũ).
- Dữ liệu seed sẵn 1 sự kiện demo `EV001` (`ON_SALE`, 2 loại vé
  VIP/STANDARD) - giữ tương thích với dữ liệu test cũ / Postman
  collection.

## API

| Method | Path | Ghi chú |
|---|---|---|
| GET | `/health` | Health check đơn giản |
| GET | `/events` | Liệt kê tất cả sự kiện |
| POST | `/events` | Tạo sự kiện mới (mặc định `DRAFT`) |
| GET | `/events/{id}` | Lấy chi tiết 1 sự kiện, 404 nếu không có |
| PUT | `/events/{id}` | Cập nhật tên/địa điểm/thời gian |
| GET | `/events/{id}/on-sale` | Endpoint tiện lợi cho ESB kiểm tra nhanh |
| POST | `/events/{id}/open-sales` | Mở bán vé, 409 nếu chuyển trạng thái không hợp lệ |
| POST | `/events/{id}/pause-sales` | Tạm dừng bán vé |
| POST | `/events/{id}/close-sales` | Đóng bán vé |
| POST | `/events/{id}/cancel` | Hủy sự kiện |

## Chạy thử

### Cách 1: Docker Compose (khuyến nghị, giống hệt CI/production)

```powershell
docker compose --profile event up --build --wait
```

Root Compose chạy `event-migrate` trước và chỉ start service ở cổng `8002`
khi migration hoàn thành thành công.

### Cách 2: Chạy trực tiếp (cần tự có PostgreSQL)

```powershell
cd services\event-service
pip install -r requirements-dev.txt
copy .env.example .env
# sua EVENT_DATABASE_URL trong .env cho khop voi Postgres cua ban
alembic upgrade head
python -m uvicorn app.main:app --port 8002 --reload
```

### Kiểm thử nhanh bằng curl

```powershell
curl http://localhost:8002/health
curl http://localhost:8002/events/EV001
curl -X POST http://localhost:8002/events -H "Content-Type: application/json" ^
  -d "{\"name\":\"Hoi thao AI\",\"location\":\"Trung tam hoi nghi\",\"startTime\":\"2026-09-15T09:00:00\",\"ticketTypes\":[{\"type\":\"STANDARD\",\"price\":100000}]}"
curl -X POST http://localhost:8002/events/EV001/pause-sales
curl -X POST http://localhost:8002/events/EV001/open-sales
```

## Test

```powershell
pip install -r requirements-dev.txt
pytest tests/unit                 # khong can Postgres
pytest tests/integration -m integration   # can Postgres that dang chay
```

## Ghi chú nâng cấp so với bản MVP trước

Bản đầu (MVP) dùng `InMemoryEventRepository` (dict trong bộ nhớ) để có
luồng chạy được sớm cho ESB gọi thử; dữ liệu mất khi restart, và
`env.py`/`alembic.ini`/`README.md`/`pyproject.toml`/`requirements-dev.txt`
vẫn là placeholder vì chưa có database thật để Alembic quản lý. Bản này
thay bằng `PostgresEventRepository` thật, đồng bộ với cách Customer
Service, Seat Inventory Service và Identity Service đã làm - dữ liệu bền
vững qua Alembic migration (kể cả bảng con `ticket_types`), không còn
placeholder ở bất kỳ tệp cấu hình nào.
