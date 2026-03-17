FROM python:3.11-slim

WORKDIR /app

COPY shared/ /shared
RUN pip install --no-cache-dir /shared

COPY workers/analytics-worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY workers/analytics-worker/app ./app

CMD ["python", "-m", "app.worker"]
