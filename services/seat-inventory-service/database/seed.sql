INSERT INTO seat.inventory_versions (event_id, inventory_version)
VALUES ('EVT-DEMO', 1)
ON CONFLICT (event_id) DO UPDATE
SET inventory_version = EXCLUDED.inventory_version,
    updated_at = clock_timestamp();

INSERT INTO seat.seats (
    event_id,
    seat_id,
    section,
    row_label,
    seat_number,
    ticket_type,
    status,
    current_reservation_id,
    resource_version
)
VALUES
    ('EVT-DEMO', 'A-01', 'A', 'A', '01', 'STANDARD', 'AVAILABLE', NULL, 1),
    ('EVT-DEMO', 'A-02', 'A', 'A', '02', 'STANDARD', 'AVAILABLE', NULL, 1),
    ('EVT-DEMO', 'A-03', 'A', 'A', '03', 'STANDARD', 'AVAILABLE', NULL, 1),
    ('EVT-DEMO', 'VIP-01', 'VIP', 'V', '01', 'VIP', 'AVAILABLE', NULL, 1),
    ('EVT-DEMO', 'VIP-02', 'VIP', 'V', '02', 'VIP', 'BLOCKED', NULL, 1)
ON CONFLICT (event_id, seat_id) DO UPDATE
SET section = EXCLUDED.section,
    row_label = EXCLUDED.row_label,
    seat_number = EXCLUDED.seat_number,
    ticket_type = EXCLUDED.ticket_type,
    status = CASE
        WHEN seat.seats.status IN ('HELD', 'SOLD') THEN seat.seats.status
        ELSE EXCLUDED.status
    END,
    current_reservation_id = CASE
        WHEN seat.seats.status = 'HELD' THEN seat.seats.current_reservation_id
        ELSE NULL
    END,
    updated_at = clock_timestamp();
