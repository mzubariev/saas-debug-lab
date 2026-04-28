#!/usr/bin/env bash
# Hold a row lock in Postgres for CHAOS_DB_LOCK_SECONDS (blocks concurrent updates on that row).
# Env: POSTGRES_CONTAINER, POSTGRES_USER, POSTGRES_DB, CHAOS_DB_LOCK_SECONDS (default 90), CHAOS_LOCK_TASK_ID (optional UUID)
set -euo pipefail

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-postgres}"
POSTGRES_USER="${POSTGRES_USER:-admin}"
POSTGRES_DB="${POSTGRES_DB:-saas}"
SEC="${CHAOS_DB_LOCK_SECONDS:-90}"
TASK_ID="${CHAOS_LOCK_TASK_ID:-}"

echo "[CHAOS] Running db_lock"
echo "[CHAOS] db_lock: holding lock ${SEC}s on ${POSTGRES_CONTAINER}"

if [[ -n "$TASK_ID" ]]; then
  if ! [[ "$TASK_ID" =~ ^[0-9a-fA-F-]{36}$ ]]; then
    echo "[CHAOS] db_lock: CHAOS_LOCK_TASK_ID must be a UUID" >&2
    exit 1
  fi
  SQL="BEGIN; SELECT 1 FROM tasks WHERE id = '${TASK_ID}'::uuid FOR UPDATE; SELECT pg_sleep(${SEC}); COMMIT;"
else
  SQL="BEGIN; SELECT id FROM tasks ORDER BY created_at DESC NULLS LAST LIMIT 1 FOR UPDATE; SELECT pg_sleep(${SEC}); COMMIT;"
fi

docker exec -d "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "$SQL" || {
  echo "[CHAOS] db_lock: could not start lock session (no tasks?). Run seed_dev.py first." >&2
  exit 1
}
echo "[CHAOS] db_lock: background session started (wait ${SEC}s or terminate backends manually)"
