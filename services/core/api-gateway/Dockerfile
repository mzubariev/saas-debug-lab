FROM python:3.11-slim

WORKDIR /app

COPY services/core/api-gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared
RUN pip install -e "/app/shared[services]"

COPY services/core/api-gateway/app ./app

# Datadog APM (`ddtrace-run`) is applied only via `docker-compose.datadog.yml` override.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--no-access-log"]
