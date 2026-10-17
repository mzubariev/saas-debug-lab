FROM python:3.14-slim

WORKDIR /app

COPY services/core/api-gateway/requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY shared/ /app/shared
RUN pip install --no-deps -e /app/shared

COPY services/core/api-gateway/app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--no-access-log"]
