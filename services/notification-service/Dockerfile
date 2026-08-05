FROM python:3.12.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN addgroup --system notification && adduser --system --ingroup notification --home /app notification

COPY services/notification-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt

COPY --chown=notification:notification services/notification-service/alembic.ini ./
COPY --chown=notification:notification services/notification-service/migrations ./migrations
COPY --chown=notification:notification services/notification-service/app ./app
COPY --chown=notification:notification services/notification-service/docker-entrypoint.sh ./docker-entrypoint.sh

RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod 0555 docker-entrypoint.sh

USER notification
EXPOSE 8007
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; from app.infrastructure.database.session import database_ready; urllib.request.urlopen('http://127.0.0.1:8007/health', timeout=2); assert database_ready()"
ENTRYPOINT ["./docker-entrypoint.sh"]
