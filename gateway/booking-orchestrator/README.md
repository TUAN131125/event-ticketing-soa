# Booking Orchestrator (ESB)

The ESB implements `contracts/esb-public-api.yaml` on port `8000`. It validates User JWTs,
orchestrates providers with short-lived Service JWTs and issues booking-bound Realtime tickets.

Run through root Compose (`docker compose --profile all up --build --wait`). For direct execution,
run the migration separately and then start `uvicorn app.main:create_app --factory --port 8000`.
Readiness is `/health/ready`; migrations never run in the application process.
