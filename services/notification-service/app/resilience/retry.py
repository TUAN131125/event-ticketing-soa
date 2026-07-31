"""Retry tu dong cho notification that bai.

Chua trien khai trong MVP (uu tien hoan thien REST/ESB va fault tolerance
o ESB truoc, nhu da thong nhat voi nhom). Rui ro con lai: neu provider
gui email tam thoi loi, hien tai khong co co che tu dong gui lai - can xu
ly thu cong hoac bo sung sau (vd doc lai cac ban ghi status=FAILED trong
bang notification.deliveries).
"""
