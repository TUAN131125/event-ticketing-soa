# Event Ticketing web applications

Workspace gồm:

- `customer-web`: UI khách hàng theo UI-01 đến UI-09 và UI-12.
- `admin-web`: Event administration UI-10, Ticket check-in UI-11, health/booking/trace operations.
- `shared-ui`: component dùng chung và generated contract types từ `contracts/esb-public-api.yaml`.

## Chạy local

```powershell
cd frontend
npm ci
npm run generate:contracts
npm run lint
npm run typecheck
npm run test
npm run build
```

Chạy riêng:

```powershell
npm run dev --workspace @event-ticketing/customer-web
npm run dev --workspace @event-ticketing/admin-web
```

Copy `.env.example` thành `.env.local` cho từng app.

## Quy tắc contract

- Business request chỉ đi qua ESB.
- Auth chỉ đi qua façade `/api/auth/*` của ESB; browser không gọi trực tiếp Identity port `8009`.
- Bản frontend hiện dùng REST polling qua ESB cho booking status; WebSocket trực tiếp tới Realtime bị tắt cho đến khi có gateway route được phê duyệt.
- Không hard-code private service URL hoặc gọi các cổng `8001`–`8009` từ browser.
- Generated files trong `shared-ui/src/generated` chỉ được tạo bằng `npm run generate:contracts`.
- `shared-ui/src/frontend-esb-contract.ts` chỉ được alias generated schemas; không khai báo wire contract viết tay.
- Chạy `npm run verify:esb-contract` để kiểm tra các operation/schema frontend cần vẫn tồn tại.

Xem:

- `FRONTEND_SCREEN_UPDATE_PLAN.md` — màn hình thêm/sửa/xóa.
- `INTEGRATION_STATUS.md` — API frontend đã khóa với ESB.
- `FRONTEND_COMPLETION_REPORT.md` — thay đổi và trạng thái kiểm tra.
