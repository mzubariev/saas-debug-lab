FROM python:3.11-slim

WORKDIR /app

COPY shared/ /shared
RUN pip install --no-cache-dir "/shared[services]"

COPY services/webhook-dispatcher/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/webhook-dispatcher/app ./app

CMD ["python", "-m", "app.run"]
