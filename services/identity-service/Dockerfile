FROM python:3.12.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system identity \
    && adduser --system --ingroup identity --home /app identity \
    && mkdir -p /app/contracts \
    && chown identity:identity /app/contracts

COPY services/identity-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt

COPY --chown=identity:identity services/identity-service/pyproject.toml services/identity-service/alembic.ini ./
COPY --chown=identity:identity services/identity-service/migrations ./migrations
COPY --chown=identity:identity services/identity-service/app ./app
COPY --chown=identity:identity services/identity-service/docker-entrypoint.sh ./docker-entrypoint.sh
COPY --chown=identity:identity dist/contracts/identity-service.yaml ./contracts/identity-service.yaml

RUN sed -i 's/\r$//' docker-entrypoint.sh \
    && chmod 0555 docker-entrypoint.sh

USER identity
EXPOSE 8009

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8009/health/ready', timeout=2)"

ENTRYPOINT ["./docker-entrypoint.sh"]
