FROM python:3.11-slim

WORKDIR /app

COPY services/core/webhook-dispatcher/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared
RUN pip install -e "/app/shared[services]"

COPY services/core/webhook-dispatcher/app ./app

CMD ["python", "-m", "app.run"]
