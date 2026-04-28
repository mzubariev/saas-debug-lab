#!/usr/bin/env bash
# Open many concurrent Postgres sessions sleeping on pg_sleep (pool / connection pressure).
# Env: POOL_CONNECTIONS (default 45), POOL_SLEEP_SEC (default 180), POSTGRES_* 
# Cleanup: kills sessions whose query contains CHAOS_DB_POOL_MARKER after hold window (or run db_pool_exhaust_cleanup.sh)
set -euo pipefail

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-postgres}"
POSTGRES_USER="${POSTGRES_USER:-admin}"
POSTGRES_DB="${POSTGRES_DB:-saas}"
N="${POOL_CONNECTIONS:-45}"
SLEEP="${POOL_SLEEP_SEC:-180}"
MARKER="chaos_db_pool"

echo "[CHAOS] Running db_pool_exhaust"
echo "[CHAOS] db_pool_exhaust: ${N} sessions × pg_sleep(${SLEEP}) marker=${MARKER}"

for _ in $(seq 1 "$N"); do
  docker exec -d "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT /* ${MARKER} */ pg_sleep(${SLEEP});" >/dev/null 2>&1 || true
done

echo "[CHAOS] db_pool_exhaust: sessions launched. Cleanup after test:"
echo "  docker exec ${POSTGRES_CONTAINER} psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE query LIKE '%${MARKER}%' AND pid <> pg_backend_pid();\""
