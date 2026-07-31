"""Xu ly concurrency.

Notification Service khong co tai nguyen tranh chap dong thoi nhu Seat
Inventory (khong ai "giu cho" mot delivery). Truong hop gan nhat - 2
webhook trung correlationId toi cung luc - da duoc xu ly bang UNIQUE
constraint (xem infrastructure/database/repositories.py), khong can
optimistic/pessimistic locking rieng. Giu file de dong bo cau truc thu
muc voi cac service khac.
"""
