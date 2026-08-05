FROM python:3.12.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN addgroup --system booking && adduser --system --ingroup booking --home /app booking

COPY services/booking-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt

COPY --chown=booking:booking services/booking-service/alembic.ini ./
COPY --chown=booking:booking services/booking-service/migrations ./migrations
COPY --chown=booking:booking services/booking-service/app ./app
COPY --chown=booking:booking libs ./libs
COPY --chown=booking:booking services/booking-service/docker-entrypoint.sh ./docker-entrypoint.sh

RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod 0555 docker-entrypoint.sh

USER booking
EXPOSE 8004
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8004/health/ready', timeout=2)"
ENTRYPOINT ["./docker-entrypoint.sh"]
