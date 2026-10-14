FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/external/external-service-simulator/requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY shared/ /app/shared
RUN pip install --no-deps -e /app/shared

COPY services/external/external-service-simulator/app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--no-access-log"]
