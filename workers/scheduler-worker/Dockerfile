FROM python:3.11-slim

WORKDIR /app

COPY shared/ /shared
RUN pip install --no-cache-dir "/shared[services]"

COPY workers/scheduler-worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY workers/scheduler-worker/app ./app

# No CMD — command is set in docker-compose.yml; Datadog APM prepends ddtrace-run in docker-compose.datadog.yml.
