#!/bin/sh
set -eu

create_service_database() {
  database_name="$1"
  role_name="$2"
  role_password="$3"

  psql --set=ON_ERROR_STOP=1 \
    --set=database_name="$database_name" \
    --set=role_name="$role_name" \
    --set=role_password="$role_password" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'role_name', :'role_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role_name') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'database_name', :'role_name')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'database_name') \gexec
SQL
}

: "${IDENTITY_DB_NAME:?IDENTITY_DB_NAME is required}"
: "${IDENTITY_DB_USER:?IDENTITY_DB_USER is required}"
: "${IDENTITY_DB_PASSWORD:?IDENTITY_DB_PASSWORD is required}"
: "${CUSTOMER_DB_NAME:?CUSTOMER_DB_NAME is required}"
: "${CUSTOMER_DB_USER:?CUSTOMER_DB_USER is required}"
: "${CUSTOMER_DB_PASSWORD:?CUSTOMER_DB_PASSWORD is required}"
: "${EVENT_DB_NAME:?EVENT_DB_NAME is required}"
: "${EVENT_DB_USER:?EVENT_DB_USER is required}"
: "${EVENT_DB_PASSWORD:?EVENT_DB_PASSWORD is required}"
: "${SEAT_DB_NAME:?SEAT_DB_NAME is required}"
: "${SEAT_DB_USER:?SEAT_DB_USER is required}"
: "${SEAT_DB_PASSWORD:?SEAT_DB_PASSWORD is required}"
: "${BOOKING_DB_NAME:?BOOKING_DB_NAME is required}"
: "${BOOKING_DB_USER:?BOOKING_DB_USER is required}"
: "${BOOKING_DB_PASSWORD:?BOOKING_DB_PASSWORD is required}"
: "${PAYMENT_DB_NAME:?PAYMENT_DB_NAME is required}"
: "${PAYMENT_DB_USER:?PAYMENT_DB_USER is required}"
: "${PAYMENT_DB_PASSWORD:?PAYMENT_DB_PASSWORD is required}"
: "${TICKET_DB_NAME:?TICKET_DB_NAME is required}"
: "${TICKET_DB_USER:?TICKET_DB_USER is required}"
: "${TICKET_DB_PASSWORD:?TICKET_DB_PASSWORD is required}"
: "${NOTIFICATION_DB_NAME:?NOTIFICATION_DB_NAME is required}"
: "${NOTIFICATION_DB_USER:?NOTIFICATION_DB_USER is required}"
: "${NOTIFICATION_DB_PASSWORD:?NOTIFICATION_DB_PASSWORD is required}"
: "${ORCHESTRATOR_DB_NAME:?ORCHESTRATOR_DB_NAME is required}"
: "${ORCHESTRATOR_DB_USER:?ORCHESTRATOR_DB_USER is required}"
: "${ORCHESTRATOR_DB_PASSWORD:?ORCHESTRATOR_DB_PASSWORD is required}"

create_service_database "$IDENTITY_DB_NAME" "$IDENTITY_DB_USER" "$IDENTITY_DB_PASSWORD"
create_service_database "$CUSTOMER_DB_NAME" "$CUSTOMER_DB_USER" "$CUSTOMER_DB_PASSWORD"
create_service_database "$EVENT_DB_NAME" "$EVENT_DB_USER" "$EVENT_DB_PASSWORD"
create_service_database "$SEAT_DB_NAME" "$SEAT_DB_USER" "$SEAT_DB_PASSWORD"
create_service_database "$BOOKING_DB_NAME" "$BOOKING_DB_USER" "$BOOKING_DB_PASSWORD"
create_service_database "$PAYMENT_DB_NAME" "$PAYMENT_DB_USER" "$PAYMENT_DB_PASSWORD"
create_service_database "$TICKET_DB_NAME" "$TICKET_DB_USER" "$TICKET_DB_PASSWORD"
create_service_database "$NOTIFICATION_DB_NAME" "$NOTIFICATION_DB_USER" "$NOTIFICATION_DB_PASSWORD"
create_service_database "$ORCHESTRATOR_DB_NAME" "$ORCHESTRATOR_DB_USER" "$ORCHESTRATOR_DB_PASSWORD"
