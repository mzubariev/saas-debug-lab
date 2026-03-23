FROM python:3.11-slim

WORKDIR /app

COPY shared/ /shared
RUN pip install --no-cache-dir /shared

COPY workers/scheduler-worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY workers/scheduler-worker/app ./app

# No CMD — command is set per-service in docker-compose:
#   scheduler-worker: celery -A app.core.celery:celery_app worker --beat --loglevel=info
#   flower:           celery -A app.core.celery:celery_app flower --port=5555
