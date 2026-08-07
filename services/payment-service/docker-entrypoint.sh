#!/bin/sh
set -eu

# Migrations belong to the dedicated `payment-migrate` job, which Compose gates the
# API on. Running them here too would race the replicas against each other.
exec uvicorn app.main:app --host 0.0.0.0 --port 8005 --workers "${PAYMENT_WEB_WORKERS:-1}"
