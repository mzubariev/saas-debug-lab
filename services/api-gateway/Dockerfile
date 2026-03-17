FROM python:3.11-slim

WORKDIR /app

COPY shared/ /shared
RUN pip install --no-cache-dir "/shared[services]"

COPY services/api-gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/api-gateway/app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
