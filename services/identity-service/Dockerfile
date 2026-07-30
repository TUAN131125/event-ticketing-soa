FROM python:3.12.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system identity \
    && adduser --system --ingroup identity identity \
    && mkdir -p /app/keys \
    && chown -R identity:identity /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

COPY pyproject.toml alembic.ini ./
COPY migrations ./migrations
COPY contracts ./contracts
COPY app ./app
COPY scripts ./scripts
COPY docker-entrypoint.sh ./

RUN sed -i 's/\r$//' docker-entrypoint.sh \
    && chmod 0555 docker-entrypoint.sh \
    && chmod 0555 scripts/*.py \
    && chown -R identity:identity /app

USER identity
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"

ENTRYPOINT ["./docker-entrypoint.sh"]
