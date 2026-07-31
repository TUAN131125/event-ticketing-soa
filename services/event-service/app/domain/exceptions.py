"""Loi thuoc domain cua Event Service."""


class EventNotFoundError(Exception):
    def __init__(self, event_id: str):
        self.event_id = event_id
        super().__init__(f"Khong tim thay su kien: {event_id}")


class InvalidStateTransitionError(Exception):
    def __init__(self, current: str, target: str):
        self.current = current
        self.target = target
        super().__init__(f"Khong the chuyen tu {current} sang {target}")
