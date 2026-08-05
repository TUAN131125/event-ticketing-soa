FROM python:3.12.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN addgroup --system event && adduser --system --ingroup event --home /app event

COPY services/event-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt

COPY --chown=event:event services/event-service/alembic.ini ./
COPY --chown=event:event services/event-service/migrations ./migrations
COPY --chown=event:event services/event-service/app ./app
COPY --chown=event:event libs ./libs
COPY --chown=event:event services/event-service/docker-entrypoint.sh ./docker-entrypoint.sh

RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod 0555 docker-entrypoint.sh

USER event
EXPOSE 8002
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8002/health/ready', timeout=2)"
ENTRYPOINT ["./docker-entrypoint.sh"]
