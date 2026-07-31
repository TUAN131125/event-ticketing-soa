"""Xac thuc chu ky webhook (vd HMAC header tu ESB) truoc khi xu ly.

Chua trien khai trong MVP: webhook hien chi duoc bao ve boi gia dinh
kien truc (ESB goi noi bo, khong lo ra ngoai internet). Diem mo rong: neu
Notification Service can mo public endpoint that, them middleware kiem
tra header chu ky (vd X-ESB-Signature) truoc khi vao toi
api/v1/webhooks.py.
"""
