FROM python:3.12.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN addgroup --system payment && adduser --system --ingroup payment --home /app payment

COPY services/payment-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt

COPY --chown=payment:payment services/payment-service/alembic.ini ./
COPY --chown=payment:payment services/payment-service/migrations ./migrations
COPY --chown=payment:payment services/payment-service/app ./app
COPY --chown=payment:payment services/payment-service/docker-entrypoint.sh ./docker-entrypoint.sh

RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod 0555 docker-entrypoint.sh

USER payment
EXPOSE 8005
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8005/health/ready', timeout=2)"
ENTRYPOINT ["./docker-entrypoint.sh"]
