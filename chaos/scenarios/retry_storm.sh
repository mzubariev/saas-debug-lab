#!/usr/bin/env bash
# retry_storm — high simulator fail rate + retry_storm.js
# Expect: overload, duplicate processing / DLQ churn
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

cleanup() {
  docker unpause webhook-dispatcher 2>/dev/null || true
  docker update --cpus=4.0 webhook-dispatcher 2>/dev/null || true
  (
    cd "$ROOT/infra"
    EXTERNAL_SIMULATOR_DEFAULT_FAIL_RATE=0 docker compose --profile core up -d --no-deps --force-recreate external-service-simulator
  ) || true
  docker exec "${POSTGRES_CONTAINER:-postgres}" psql -U "${POSTGRES_USER:-admin}" -d "${POSTGRES_DB:-saas}" -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid <> pg_backend_pid() AND (query LIKE '%chaos_db_pool%' OR query LIKE '%FOR UPDATE%');" \
    || true
  curl -sS -X DELETE "http://localhost:8474/proxies/mailhog-smtp/toxics/latency" || true
}
trap cleanup EXIT

echo "=== Scenario: retry_storm ==="
echo "Primitives: chaos/primitives/retry_storm.sh"
echo "Load: make load-retry-storm CHAOS=1"
echo "Expected pattern: retry storm, DLQ growth, Celery replay pressure"

bash "$ROOT/chaos/primitives/retry_storm.sh"
make load-retry-storm CHAOS=1 || true

echo "[CHAOS] retry_storm: load finished. EXIT trap restores EXTERNAL_SIMULATOR_DEFAULT_FAIL_RATE=0."
