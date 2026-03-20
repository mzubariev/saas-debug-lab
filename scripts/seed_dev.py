#!/usr/bin/env python3
"""
Seed script — small development dataset.

Creates:
  - 2 users:  admin/admin123 (role=admin), user/user123 (role=user)
  - 10 tasks spread across all three statuses

Idempotent: users and tasks are inserted with ON CONFLICT DO NOTHING.
Fixed UUIDs are used for tasks so re-runs don't duplicate rows.

Usage:
  # Against the Docker Postgres (port forwarded to localhost):
  DATABASE_URL=postgresql://admin:admin@localhost:5432/saas python scripts/seed_dev.py

  # Or run inside the network via docker-compose exec:
  docker compose -f infra/docker-compose.yml run --rm auth-migrate \
      python /scripts/seed_dev.py
"""
import os
import sys

import psycopg2
from passlib.context import CryptContext

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://admin:admin@localhost:5432/saas",
)

# ─── Seed data ────────────────────────────────────────────────────────────────

USERS = [
    # (username, plaintext_password, role)
    ("admin", "admin123", "admin"),
    ("user",  "user123",  "user"),
]

# Fixed UUIDs keep the script idempotent across re-runs.
TASKS = [
    # (uuid, title, status)
    ("11111111-0000-0000-0000-000000000001", "Set up CI/CD pipeline",           "created"),
    ("11111111-0000-0000-0000-000000000002", "Configure Prometheus alerting",   "created"),
    ("11111111-0000-0000-0000-000000000003", "Document REST API endpoints",     "created"),
    ("11111111-0000-0000-0000-000000000004", "Implement rate limiting in Nginx","in_progress"),
    ("11111111-0000-0000-0000-000000000005", "Add OpenTelemetry tracing",       "in_progress"),
    ("11111111-0000-0000-0000-000000000006", "Write load testing scenarios",    "in_progress"),
    ("11111111-0000-0000-0000-000000000007", "Fix auth token expiry bug",       "completed"),
    ("11111111-0000-0000-0000-000000000008", "Deploy Nginx reverse proxy",      "completed"),
    ("11111111-0000-0000-0000-000000000009", "Add Kafka dead-letter queue",     "completed"),
    ("11111111-0000-0000-0000-000000000010", "Create staging environment",      "completed"),
]


def run() -> None:
    print(f"Connecting to {DATABASE_URL} …")
    try:
        conn = psycopg2.connect(DATABASE_URL)
    except psycopg2.OperationalError as exc:
        print(f"ERROR: could not connect — {exc}", file=sys.stderr)
        sys.exit(1)

    conn.autocommit = True
    cur = conn.cursor()

    # ── Users ──────────────────────────────────────────────────────────────
    print("\nSeeding users …")
    for username, password, role in USERS:
        cur.execute(
            """
            INSERT INTO users (username, hashed_password, role)
            VALUES (%s, %s, %s)
            ON CONFLICT (username) DO NOTHING
            """,
            (username, _pwd.hash(password), role),
        )
        print(f"  {'OK' if cur.rowcount else 'skip (exists)':16s}  {username}  ({role})")

    # ── Tasks ──────────────────────────────────────────────────────────────
    print("\nSeeding tasks …")
    for task_id, title, status in TASKS:
        cur.execute(
            """
            INSERT INTO tasks (id, title, status)
            VALUES (%s::uuid, %s, %s::taskstatus)
            ON CONFLICT (id) DO NOTHING
            """,
            (task_id, title, status),
        )
        print(f"  {'OK' if cur.rowcount else 'skip (exists)':16s}  [{status:<12}]  {title}")

    cur.close()
    conn.close()
    print(f"\nDone. Seeded {len(USERS)} users and {len(TASKS)} tasks.")


if __name__ == "__main__":
    run()
