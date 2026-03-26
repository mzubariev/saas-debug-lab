FROM python:3.11-slim

WORKDIR /app

COPY shared/ /shared
RUN pip install --no-cache-dir /shared

COPY migrations/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY migrations/alembic.ini .
COPY migrations/alembic ./alembic

CMD ["alembic", "upgrade", "head"]
