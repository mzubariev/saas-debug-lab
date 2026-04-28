#!/usr/bin/env bash
# db_pool_exhaustion — many sleeping DB sessions + concurrency
# Expect: timeouts, hanging requests
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-postgres}"
POSTGRES_USER="${POSTGRES_USER:-admin}"
POSTGRES_DB="${POSTGRES_DB:-saas}"

echo "=== Scenario: db_pool_exhaustion ==="
echo "Primitives: chaos/primitives/db_pool_exhaust.sh"
echo "Load: make load-concurrency"
echo "Expected pattern: connection pool exhaustion, 5xx/timeouts"

bash "$ROOT/chaos/primitives/db_pool_exhaust.sh"
sleep 3
make load-concurrency || true

echo "[CHAOS] db_pool_exhaustion: terminating chaos sleep sessions…"
docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE query LIKE '%chaos_db_pool%' AND pid <> pg_backend_pid();" \
  || true

echo "[CHAOS] db_pool_exhaustion: complete"
