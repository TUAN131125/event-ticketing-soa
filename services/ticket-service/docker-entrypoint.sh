#!/bin/sh
set -eu

exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8006 --workers "${TICKET_WEB_WORKERS:-1}"
