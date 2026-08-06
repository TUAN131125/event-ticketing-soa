# Báo cáo V4 — Identity qua ESB và đồng bộ Frontend

## 1. Mục tiêu

Bản V4 sửa ranh giới public entrypoint theo quyết định kiến trúc của dự án:

```text
Browser Frontend
  → ESB port 8000: /api/auth/* và /api/* nghiệp vụ
  → Identity Service port 8009: /auth/*
```

Identity Service vẫn sở hữu mật khẩu, role, access token, refresh session, khóa tài khoản và JWKS. ESB không xác thực mật khẩu, không phát hành token và không lưu refresh session.

Nguồn provider được đồng bộ từ contract và runtime Identity hiện tại trên nhánh `main` của repository:

- `POST /auth/register` trả `User`;
- `POST /auth/login` và `POST /auth/refresh` trả `TokenResponse` gồm `accessToken`, `tokenType`, `expiresIn`, `csrfToken`, `user`;
- `POST /auth/logout` trả `204`;
- `GET /auth/me` trả `User`;
- refresh và CSRF cookie dùng path `/auth`, do đó ESB phải đổi thành `/api/auth` khi proxy ra browser.

## 2. Thay đổi ESB

### 2.1. Public auth façade

Bổ sung đúng năm operation:

```text
POST /api/auth/register
POST /api/auth/login
POST /api/auth/refresh
POST /api/auth/logout
GET  /api/auth/me
```

`IdentityProxyAdapter` chỉ cho phép năm path provider tương ứng và chuyển tiếp có kiểm soát:

- `Authorization`;
- `Cookie`;
- `X-CSRF-Token`;
- `Idempotency-Key`;
- `X-Correlation-ID`;
- `traceparent`.

Adapter không dùng service JWT của ESB cho browser auth. Nó giữ nhiều header `Set-Cookie`, bỏ `Domain` nội bộ, đổi `Path=/auth` thành `Path=/api/auth`, đồng thời giữ `HttpOnly`, `Secure`, `SameSite`, `Max-Age`, `Cache-Control` và `Pragma`.

### 2.2. Response validation và lỗi

ESB kiểm tra response thành công của Identity bằng Pydantic:

- register → `User`;
- login/refresh → `TokenResponse`;
- me → `User`.

Error body từ Identity phải khớp `ErrorResponse`; response sai contract được chuyển thành `502 IDENTITY_PROTOCOL_ERROR`. Password, JWT, cookie và CSRF token không được ghi log.

### 2.3. OpenAPI security

Canonical/runtime OpenAPI khai báo:

- `BearerAuth` cho booking, ticket, customer profile, admin, check-in, trace và WS-ticket;
- `RefreshCookie` + `CsrfCookie` + `CsrfHeader` cho refresh/logout;
- register/login/event read/health là public.

Login, refresh và logout còn khai báo `Set-Cookie`, `Cache-Control` và `Pragma` trong response headers.

OpenAPI tiếp tục được sinh từ route FastAPI thật; không tải YAML để che runtime schema.

## 3. Thay đổi Frontend

- Customer Web và Admin Web chỉ đọc `VITE_ESB_API_URL`.
- Xóa `VITE_IDENTITY_API_URL`, `VITE_REALTIME_WS_URL` và các Docker build args tương ứng.
- Auth client gọi `/api/auth/register|login|refresh|logout|me` trên ESB.
- Auth types được lấy từ generated ESB public contract, không lấy provider Identity contract làm browser API.
- Access token giữ trong memory; CSRF token giữ trong `sessionStorage`; refresh cookie vẫn là HttpOnly cookie do Identity phát hành qua ESB.
- Direct WebSocket tới port `8008` bị tắt; booking status tạm dùng REST polling qua ESB.
- Compose build của hai frontend chỉ nhận `VITE_ESB_API_URL`.

## 4. Contract generation

Hai generator đều đọc đúng canonical paths:

```text
contracts/esb-public-api.yaml
contracts/providers/identity-service.yaml
contracts/providers/realtime-status-service.yaml
contracts/providers/realtime-status.asyncapi.yaml
```

Python fallback hiện sinh đủ bốn file:

```text
esb-public-api.ts
identity-service.ts
realtime-service.ts
realtime-messages.ts
```

Verifier kiểm tra SHA-256 của cả bốn generated artifacts, 29 operation frontend dùng, security metadata, build inputs và Compose args.

## 5. Cấu hình host và Docker

- Chạy trực tiếp trên host: dùng `.env.host.example` và `uvicorn ... --env-file .env`.
- Chạy Docker network: dùng tên service thực của root Compose (`identity`, `customer`, `event`, `seat`, `booking`, `payment`, `ticket`, `notification`, `realtime`).
- Root `.env.example` bổ sung `ESB_IDENTITY_SERVICE_URL=http://identity:8009`.
- Root Compose không truyền URL Identity/Realtime vào frontend build.

## 6. Kiểm tra đã chạy

```text
Python compileall:                          PASS
ESB pytest:                                 74 passed
FastAPI OpenAPI parity:                     PASS
OpenAPI inventory:                          30 paths / 33 operations
Frontend consumer verifier (Python):        PASS — 29 operations
Generated contract hashes (4 artifacts):   PASS
Targeted strict TypeScript auth/contracts:  PASS
Node script syntax:                         PASS
Compose/OpenAPI/YAML parsing:               PASS
Seat WSDL/XSD contract tests:               PASS (nằm trong 74 tests)
```

`npm ci` chưa chạy được trong môi trường tạo artifact vì registry nội bộ trả `404` cho `vitest@3.2.6`. Docker không có trong runtime nên Docker build, PostgreSQL integration và browser E2E chưa được tuyên bố PASS.

## 7. Trạng thái

```text
Identity contract theo GitHub:          ALIGNED
Frontend gọi Identity trực tiếp:        REMOVED
Frontend → ESB → Identity:              IMPLEMENTED
ESB Bearer/cookie/CSRF OpenAPI:          IMPLEMENTED
Clean generator paths:                  FIXED
Host/Docker env wiring:                 FIXED IN OVERLAY
Core/unit/contract:                     PASS
Docker/PostgreSQL/full browser E2E:      NOT_RUN
```

Bản này là repository overlay V4. Sau khi merge vào full repository, phải chạy các release gate trong `IDENTITY_ESB_FRONTEND_V4_MERGE_INSTRUCTIONS.md` trước khi gắn nhãn `READY_FOR_LOCAL_DEMO`.
