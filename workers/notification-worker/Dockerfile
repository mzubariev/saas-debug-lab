FROM python:3.11-slim

WORKDIR /app

COPY workers/notification-worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared
RUN pip install -e "/app/shared[services]"

COPY workers/notification-worker/app ./app

CMD ["python", "-m", "app.worker"]
