FROM python:3.12.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN addgroup --system customer && adduser --system --ingroup customer --home /app customer

COPY services/customer-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt

COPY --chown=customer:customer services/customer-service/alembic.ini ./
COPY --chown=customer:customer services/customer-service/migrations ./migrations
COPY --chown=customer:customer services/customer-service/app ./app
COPY --chown=customer:customer libs ./libs
COPY --chown=customer:customer services/customer-service/docker-entrypoint.sh ./docker-entrypoint.sh

RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod 0555 docker-entrypoint.sh

USER customer
EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health/ready', timeout=2)"
ENTRYPOINT ["./docker-entrypoint.sh"]
