#!/bin/sh
set -eu

exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8003 --workers "${SEAT_WEB_WORKERS:-1}" --proxy-headers --no-access-log
