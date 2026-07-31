# Customer Service

Customer Service quản lý hồ sơ khách hàng (tạo mới, tra cứu, cập nhật thông
tin liên hệ, vô hiệu hóa). Đây là service T2 (theo phân loại DOC-04 của
nhóm): không có tài nguyên tranh chấp đồng thời như Seat Inventory, nên
service ưu tiên sự đơn giản và rõ ràng của REST + PostgreSQL thay vì các cơ
chế khóa nâng cao.

## Kiến trúc

Clean Architecture / layered, cùng phong cách với các service khác trong
repo:

```text
HTTP (FastAPI)
    |
    v
app/api            - nhan request, tra response (khong chua logic)
    |
    v
app/application     - use case (create/get/update/deactivate customer)
    |
    v
app/domain          - entity + rule thuan nghiep vu, khong biet FastAPI/DB
    |
    v
app/repositories     - interface (Protocol) CustomerRepository
    |
    v
app/infrastructure/database - PostgresCustomerRepository (SQLAlchemy 2.0)
    |
    v
PostgreSQL (schema "customer")
```

Domain và application layer chỉ phụ thuộc vào `CustomerRepository`
(Protocol) - không biết dữ liệu lưu ở đâu. Nhờ vậy khi nâng cấp từ
`InMemoryCustomerRepository` (bản MVP ban đầu) lên `PostgresCustomerRepository`
thật, không phải sửa gì ở tầng `application`/`api`, chỉ đổi 1 dòng trong
`app/dependencies.py`.

`InMemoryCustomerRepository` vẫn còn trong code nhưng chỉ dùng cho
`tests/unit` (chạy nhanh, không cần Postgres) - app thật (`app/main.py`)
luôn dùng `PostgresCustomerRepository`.

## Dữ liệu

- Schema riêng `customer` trong PostgreSQL, quản lý bằng Alembic
  (`migrations/versions/0001_initial_schema.py`).
- Bảng `customer.customers`: `id` (dạng `C001`, `C002`, ...), `name`,
  `email` (unique), `phone`, `status` (`ACTIVE`/`INACTIVE`), `created_at`.
- `id` được sinh bằng PostgreSQL `SEQUENCE customer.customer_id_seq` -
  sinh tại tầng database nên vẫn đúng khi chạy nhiều worker/container
  cùng lúc (khác với biến đếm trong bộ nhớ của bản MVP cũ).
- Dữ liệu seed sẵn 1 khách hàng demo `C001` (giữ tương thích với dữ liệu
  test cũ / Postman collection).

## API

| Method | Path | Ghi chú |
|---|---|---|
| GET | `/health` | Health check đơn giản |
| POST | `/customers` | Tạo khách hàng, 409 nếu email trùng |
| GET | `/customers/{id}` | Lấy thông tin 1 khách hàng, 404 nếu không có |
| PUT | `/customers/{id}` | Cập nhật tên/email/sđt |
| GET | `/customers/{id}/exists` | Endpoint tiện lợi cho ESB kiểm tra nhanh |
| POST | `/customers/{id}/deactivate` | Vô hiệu hóa (xóa mềm) |

## Chạy thử

### Cách 1: Docker Compose (khuyến nghị, giống hệt CI/production)

```powershell
cd services\customer-service
docker compose up --build
```

Compose tự khởi động PostgreSQL, chạy `alembic upgrade head` (qua
`docker-entrypoint.sh`) rồi mới start service ở cổng `8001`.

### Cách 2: Chạy trực tiếp (cần tự có PostgreSQL)

```powershell
cd services\customer-service
pip install -r requirements-dev.txt
copy .env.example .env
# sua CUSTOMER_DATABASE_URL trong .env cho khop voi Postgres cua ban
alembic upgrade head
python -m uvicorn app.main:app --port 8001 --reload
```

### Kiểm thử nhanh bằng curl

```powershell
curl http://localhost:8001/health
curl http://localhost:8001/customers/C001
curl -X POST http://localhost:8001/customers -H "Content-Type: application/json" ^
  -d "{\"name\":\"Tran Thi B\",\"email\":\"b@example.com\",\"phone\":\"0909999999\"}"
```

## Test

```powershell
pip install -r requirements-dev.txt
pytest tests/unit                 # khong can Postgres
pytest tests/integration -m integration   # can Postgres that dang chay
```

## Ghi chú nâng cấp so với bản MVP trước

Bản đầu (MVP) dùng `InMemoryCustomerRepository` (dict trong bộ nhớ) để có
luồng chạy được sớm cho ESB gọi thử; dữ liệu mất khi restart. Bản này thay
bằng `PostgresCustomerRepository` thật, đồng bộ với cách Seat Inventory
Service và Identity Service đã làm - dữ liệu bền vững qua Alembic
migration, không còn placeholder ở `README.md`, `pyproject.toml`,
`alembic.ini`, `requirements-dev.txt`.
