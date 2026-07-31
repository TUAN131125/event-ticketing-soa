FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY docker-entrypoint.sh ./

RUN sed -i 's/\r$//' docker-entrypoint.sh \
    && chmod 0555 docker-entrypoint.sh

EXPOSE 8002

ENTRYPOINT ["./docker-entrypoint.sh"]
