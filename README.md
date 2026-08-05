# Event Ticketing SOA

Monorepo cho hệ thống đặt vé sự kiện theo kiến trúc SOA/ESB. Thư mục
`contracts/` là nguồn sự thật duy nhất cho các contract runtime.

## Chạy local bằng Docker Compose

1. Build contract runtime:

   ```powershell
   python contracts/scripts/validate_contracts.py
   python contracts/scripts/build_contracts.py
   ```

2. Sao chép `.env.example` thành `.env`, thay các mật khẩu/token mẫu và đặt
   các RSA key local trong `local-secrets/` theo các đường dẫn khai báo trong
   `.env`. Repository không tự sinh signing key.

3. Khởi động toàn hệ thống:

   ```powershell
   docker compose --profile all up --build --wait
   ```

   Có thể thay `all` bằng `identity`, `customer`, `event`, `seat`, `booking`,
   `payment`, `ticket`, `notification`, `orchestrator`, `realtime`, `backend`
   hoặc `frontend`. Mỗi backend có một migration job one-shot; application chỉ
   khởi động sau khi migration hoàn thành thành công.

4. Dọn môi trường local:

   ```powershell
   docker compose down --volumes --remove-orphans
   ```

## Cổng chuẩn

ESB `8000`, Customer `8001`, Event `8002`, Seat `8003`, Booking `8004`,
Payment `8005`, Ticket `8006`, Notification `8007`, Realtime `8008` và
Identity `8009`. Customer Web dùng `3000`; Admin Web dùng `3001`.

Không commit `.env`, private key, certificate, token hoặc artifact build.
