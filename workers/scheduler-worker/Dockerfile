FROM python:3.11-slim

WORKDIR /app

COPY workers/scheduler-worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared
RUN pip install -e "/app/shared[services]"

COPY workers/scheduler-worker/app ./app

# No CMD — command is set in docker-compose.yml.
