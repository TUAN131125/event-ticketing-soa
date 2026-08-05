FROM python:3.12.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY gateway/booking-orchestrator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt

FROM python:3.12.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN addgroup --system orchestrator \
    && adduser --system --ingroup orchestrator --home /app orchestrator

COPY --from=builder /opt/venv /opt/venv
COPY --chown=orchestrator:orchestrator gateway/booking-orchestrator/pyproject.toml gateway/booking-orchestrator/alembic.ini ./
COPY --chown=orchestrator:orchestrator gateway/booking-orchestrator/alembic ./alembic
COPY --chown=orchestrator:orchestrator gateway/booking-orchestrator/app ./app
COPY --chown=orchestrator:orchestrator libs ./libs
COPY --chown=orchestrator:orchestrator dist/contracts ./contracts

USER orchestrator
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2)"

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
