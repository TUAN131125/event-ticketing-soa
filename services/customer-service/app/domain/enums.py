"""Cac enum thuoc domain cua Customer Service."""
from enum import Enum


class CustomerStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    # Du trong contracts/openapi/customer-service.yaml (GD5) da khai bao gia
    # tri nay, hien CHUA co endpoint nao gan trang thai ANONYMIZED (xoa/an
    # danh du lieu theo yeu cau GDPR-style). Giu enum de khop schema Customer
    # that, nhung day la gap da biet - xem README muc "Gap con lai".
    ANONYMIZED = "ANONYMIZED"


class ConsentChannel(str, Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"
