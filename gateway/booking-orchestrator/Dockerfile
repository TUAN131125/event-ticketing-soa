# Build context is the repository root: the ESB image needs `libs/` for the one-shot
# local seed job in addition to its own package. Every COPY is therefore spelled out
# from the repository root, and only runtime material is copied — no tests, reports,
# local secrets, .env files or PEM keys.
FROM python:3.12-slim AS builder
WORKDIR /app
COPY gateway/booking-orchestrator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --prefix=/install --requirement requirements.txt

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN useradd --system --uid 10001 --home-dir /app esb

COPY --from=builder /install /usr/local

COPY --chown=esb:esb gateway/booking-orchestrator/alembic.ini ./alembic.ini
COPY --chown=esb:esb gateway/booking-orchestrator/alembic ./alembic
COPY --chown=esb:esb gateway/booking-orchestrator/app ./app
# Only the XSD is read at runtime (ESB_SEAT_PROVIDER_XSD_PATH); the WSDL and the public
# OpenAPI document are build/test-time artefacts. This is the same canonical file the Seat
# Inventory image copies, so both sides validate against one schema.
COPY --chown=esb:esb contracts/seat-inventory.xsd ./contracts/seat-inventory.xsd
# Required by the `seed-local` compose profile, which mounts scripts/seed_local.py next
# to the packaged libs/ directory and imports libs.platform_security from it.
COPY --chown=esb:esb libs ./libs

USER esb
EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
