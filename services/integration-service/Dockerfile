FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY shared/ /shared
RUN pip install --no-cache-dir "/shared[services]"

COPY services/integration-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/integration-service/app ./app

CMD ["ddtrace-run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
