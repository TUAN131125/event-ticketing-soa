"""Idempotency cho webhook.

Da trien khai: chong xu ly trung 1 correlationId (xem domain/rules.py -
ensure_correlation_not_duplicate - va UNIQUE constraint tren cot
correlation_id trong migration 0001). Day la nang cap that su so voi ban
MVP truoc day (mot set trong bo nho, mat khi restart) - gio dedup ben
vung qua lan restart vi luu that trong PostgreSQL.
"""
