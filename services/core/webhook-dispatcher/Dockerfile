FROM python:3.14-slim

WORKDIR /app

COPY services/core/webhook-dispatcher/requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY shared/ /app/shared
RUN pip install --no-deps -e /app/shared

COPY services/core/webhook-dispatcher/app ./app

CMD ["python", "-m", "app.run"]
