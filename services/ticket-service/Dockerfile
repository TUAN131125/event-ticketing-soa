FROM python:3.12.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN addgroup --system ticket && adduser --system --ingroup ticket --home /app ticket

COPY services/ticket-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt

COPY --chown=ticket:ticket services/ticket-service/alembic.ini ./
COPY --chown=ticket:ticket services/ticket-service/migrations ./migrations
COPY --chown=ticket:ticket services/ticket-service/app ./app
COPY --chown=ticket:ticket services/ticket-service/docker-entrypoint.sh ./docker-entrypoint.sh

RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod 0555 docker-entrypoint.sh

USER ticket
EXPOSE 8006
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8006/health/ready', timeout=2)"
ENTRYPOINT ["./docker-entrypoint.sh"]
