"""Phan quyen (RBAC don gian) trong Notification Service.

Viec kiem tra role thuc te nam trong `security/authentication.py`
(`require_role(*roles)`), noi dependency co the truy cap Principal ngay
sau khi xac thuc JWT - tach 2 file rieng (authentication vs authorization)
chi de dong bo cau truc thu muc voi cac service khac trong repo; logic
khong lap lai o day.

Quy uoc role dung cho Notification Service (Muc 2 dac ta SVC-08, cot
"Caller chinh" = Admin/Ops cho NOT-05/07/08/09):
- "admin": duoc phep tat ca (bao gom PUT /templates/{code})
- "ops": duoc phep xem/retry delivery (GET/POST /deliveries*), KHONG sua
  template
"""
ADMIN_ROLES = ("admin",)
OPS_ROLES = ("admin", "ops")
