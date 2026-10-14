FROM python:3.14-slim

WORKDIR /app

COPY workers/notification-worker/requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY shared/ /app/shared
RUN pip install --no-deps -e /app/shared

COPY workers/notification-worker/app ./app

CMD ["python", "-m", "app.worker"]
