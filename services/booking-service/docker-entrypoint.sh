#!/bin/sh
set -eu

# Migrations belong to the dedicated `booking-migrate` job, which Compose gates the API on.
# Running them here too would race the replicas against each other.
exec uvicorn app.main:app --host 0.0.0.0 --port 8004 --workers "${BOOKING_WEB_WORKERS:-1}"
