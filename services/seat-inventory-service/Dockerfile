FROM python:3.12.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system seat \
    && adduser --system --ingroup seat --home /app seat \
    && mkdir -p /app/contracts \
    && chown seat:seat /app/contracts

COPY services/seat-inventory-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt

COPY --chown=seat:seat services/seat-inventory-service/alembic.ini ./
COPY --chown=seat:seat services/seat-inventory-service/migrations ./migrations
COPY --chown=seat:seat services/seat-inventory-service/app ./app
COPY --chown=seat:seat libs ./libs
COPY --chown=seat:seat services/seat-inventory-service/docker-entrypoint.sh ./docker-entrypoint.sh
# Straight from the canonical source, not from dist/: dist is a generated artifact that a
# local build has no reason to have refreshed, and a stale copy here would silently give
# Seat and the ESB two different schemas.
COPY --chown=seat:seat contracts/seat-inventory.wsdl ./contracts/seat-inventory.wsdl
COPY --chown=seat:seat contracts/seat-inventory.xsd ./contracts/seat-inventory.xsd

RUN sed -i 's/\r$//' docker-entrypoint.sh \
    && chmod 0555 docker-entrypoint.sh

USER seat
EXPOSE 8003

HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8003/health/ready', timeout=2)"

ENTRYPOINT ["./docker-entrypoint.sh"]
