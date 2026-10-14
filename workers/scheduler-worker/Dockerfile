FROM python:3.14-slim

WORKDIR /app

COPY workers/scheduler-worker/requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY shared/ /app/shared
RUN pip install --no-deps -e /app/shared

COPY workers/scheduler-worker/app ./app

# No CMD — command is set in docker-compose.yml.
