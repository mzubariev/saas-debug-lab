#!/usr/bin/env python3
"""
Seed script — large dataset for load testing.

Creates:
  - 2 users:  admin/admin123 (role=admin), user/user123 (role=user)
  - N tasks   (default 1 200) distributed across all three statuses

Task distribution (configurable via env vars):
  SEED_CREATED      — tasks in 'created'     state  (default 400)
  SEED_IN_PROGRESS  — tasks in 'in_progress' state  (default 400)
  SEED_COMPLETED    — tasks in 'completed'   state  (default 400)

This script TRUNCATES the tasks table before inserting to give a clean
baseline. Users are upserted (ON CONFLICT DO NOTHING) so existing
credentials are preserved.

Usage:
  # Default counts against the Docker Postgres:
  DATABASE_URL=postgresql://admin:admin@localhost:5432/saas python scripts/seed_load.py

  # Custom counts:
  SEED_CREATED=1000 SEED_IN_PROGRESS=500 SEED_COMPLETED=500 \\
      DATABASE_URL=postgresql://admin:admin@localhost:5432/saas python scripts/seed_load.py
"""
import os
import random
import sys
import uuid
from itertools import cycle

import psycopg
from passlib.context import CryptContext

_pwd = CryptContext(schemes=["argon2"], deprecated="auto")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://admin:admin@localhost:5432/saas",
)

SEED_CREATED     = int(os.environ.get("SEED_CREATED",     400))
SEED_IN_PROGRESS = int(os.environ.get("SEED_IN_PROGRESS", 400))
SEED_COMPLETED   = int(os.environ.get("SEED_COMPLETED",   400))

# ─── Title vocabulary ─────────────────────────────────────────────────────────

_VERBS = [
    "Implement", "Configure", "Deploy", "Fix", "Investigate",
    "Monitor",   "Optimize",  "Review", "Update",  "Add",
    "Remove",    "Refactor",  "Document", "Test",  "Migrate",
    "Scale",     "Audit",     "Integrate", "Benchmark", "Harden",
]

_ADJECTIVES = [
    "", "", "",           # weight toward no adjective
    "legacy ", "broken ", "slow ", "critical ", "production ",
    "staging ", "new ",   "distributed ", "async ",
]

_COMPONENTS = [
    "auth service",       "task service",        "Kafka consumer",
    "Redis cache",        "Postgres index",      "API gateway",
    "Nginx config",       "rate limiter",        "Celery beat schedule",
    "webhook retry logic","notification pipeline","Jaeger trace sampling",
    "Prometheus scrape",  "Grafana dashboard",   "Elasticsearch mapping",
    "CI/CD pipeline",     "Docker Compose",      "SSL certificate",
    "database backup",    "connection pool",     "JWT validation",
    "dead-letter queue",  "Toxiproxy config",    "Fluent Bit parser",
    "health check endpoint","Alembic migration", "seed data script",
    "load test scenario", "OpenTelemetry span",  "metrics endpoint",
]


def _gen_title() -> str:
    verb = random.choice(_VERBS)
    adj  = random.choice(_ADJECTIVES)
    comp = random.choice(_COMPONENTS)
    return f"{verb} {adj}{comp}".strip()


# ─── Users ────────────────────────────────────────────────────────────────────

_USERS = [
    ("admin", "admin123", "admin"),
    ("user",  "user123",  "user"),
]


def run() -> None:
    total = SEED_CREATED + SEED_IN_PROGRESS + SEED_COMPLETED
    print(
        f"Connecting to {DATABASE_URL} …\n"
        f"Plan: {SEED_CREATED} created + {SEED_IN_PROGRESS} in_progress "
        f"+ {SEED_COMPLETED} completed = {total} tasks"
    )

    try:
        conn = psycopg.connect(DATABASE_URL)
    except psycopg.OperationalError as exc:
        print(f"ERROR: could not connect — {exc}", file=sys.stderr)
        sys.exit(1)

    conn.autocommit = False

    with conn.cursor() as cur:

        # ── Users ──────────────────────────────────────────────────────────
        print("\nSeeding users …")
        for username, password, role in _USERS:
            cur.execute(
                """
                INSERT INTO users (username, hashed_password, role)
                VALUES (%s, %s, %s)
                ON CONFLICT (username) DO NOTHING
                """,
                (username, _pwd.hash(password), role),
            )
            print(f"  {username} ({role})")

        # ── Tasks ──────────────────────────────────────────────────────────
        print("\nTruncating tasks table …")
        cur.execute("TRUNCATE TABLE tasks RESTART IDENTITY CASCADE")

        print(f"Inserting {total} tasks …")

        rows: list[tuple[str, str, str]] = []
        for status, count in [
            ("created", SEED_CREATED),
            ("in_progress", SEED_IN_PROGRESS),
            ("completed", SEED_COMPLETED),
        ]:
            for _ in range(count):
                rows.append((str(uuid.uuid4()), _gen_title(), status))

        random.shuffle(rows)

        with cur.copy(
            "COPY tasks (id, title, status) FROM STDIN"
        ) as copy:
            for i, row in enumerate(rows, 1):
                copy.write_row(row)
                if i % 500 == 0:
                    print(f"  … {i}/{total}", end="\r", flush=True)

    conn.commit()
    conn.close()

    print(
        f"\nDone. Inserted {total} tasks "
        f"({SEED_CREATED} created, "
        f"{SEED_IN_PROGRESS} in_progress, "
        f"{SEED_COMPLETED} completed)."
    )


if __name__ == "__main__":
    run()
