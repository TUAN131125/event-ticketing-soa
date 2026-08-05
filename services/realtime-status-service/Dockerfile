FROM python:3.12.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN addgroup --system realtime && adduser --system --ingroup realtime --home /app realtime

COPY services/realtime-status-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt

COPY --chown=realtime:realtime services/realtime-status-service/app ./app

USER realtime
EXPOSE 8008
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8008/health/ready', timeout=2)"
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8008", "--workers", "1", "--no-access-log", "--timeout-graceful-shutdown", "10"]
