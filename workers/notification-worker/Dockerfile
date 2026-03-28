FROM python:3.11-slim

WORKDIR /app

COPY shared/ /shared
RUN pip install --no-cache-dir "/shared[services]"

COPY workers/notification-worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY workers/notification-worker/app ./app

CMD ["python", "-m", "app.worker"]
