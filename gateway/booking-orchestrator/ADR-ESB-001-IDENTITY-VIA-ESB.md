# ADR-ESB-001 — Identity chỉ được truy cập qua ESB

- **Trạng thái:** Accepted
- **Quyết định thay thế:** `ADR-ESB-001-IDENTITY-PUBLIC-EXCEPTION.md`

## Bối cảnh

Baseline của dự án quy định browser chỉ biết public entrypoint của ESB. Identity Service vẫn là service độc lập và là nguồn có thẩm quyền đối với tài khoản, mật khẩu, role, access JWT, refresh session và JWKS, nhưng không được public trực tiếp cho frontend.

## Quyết định

Frontend gọi duy nhất các façade sau trên ESB port `8000`:

```text
POST /api/auth/register
POST /api/auth/login
POST /api/auth/refresh
POST /api/auth/logout
GET  /api/auth/me
```

ESB chuyển tiếp tới Identity port `8009`:

```text
POST /auth/register
POST /auth/login
POST /auth/refresh
POST /auth/logout
GET  /auth/me
```

ESB không kiểm tra password, không phát hành token, không thay đổi role và không lưu refresh session. ESB chỉ:

- giới hạn đúng năm operation auth đã duyệt;
- truyền `Authorization`, `Cookie`, `X-CSRF-Token`, `Idempotency-Key`, Correlation ID và `traceparent`;
- bảo toàn nhiều header `Set-Cookie`;
- đổi cookie path từ `/auth` thành `/api/auth` để browser gửi cookie về public ESB façade;
- giữ `HttpOnly`, `Secure`, `SameSite`, `Max-Age` và các header chống cache;
- chuẩn hóa lỗi transport mà không log password, JWT, refresh cookie hoặc CSRF token.

## Hệ quả

- Frontend chỉ cấu hình `VITE_ESB_API_URL`.
- Port `8009` không phải browser/public API contract; frontend và các file build chỉ cấu hình ESB port `8000`.
- OpenAPI ESB mô tả `BearerAuth`, `RefreshCookie`, `CsrfCookie` và `CsrfHeader`.
- Identity canonical contract vẫn tồn tại như provider contract của ESB và không được frontend import để gọi trực tiếp.
