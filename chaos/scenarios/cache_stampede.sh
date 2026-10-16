#!/usr/bin/env bash
# cache_stampede — cache_flush + spike_traffic
# Expect: High Latency, System Overload (cold cache + burst)
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

echo "=== Scenario: cache_stampede ==="
echo "Primitives: chaos/primitives/cache_flush.sh"
echo "Load: make load-spike CHAOS=1"
echo "Expected pattern: High Latency, System Overload / cache miss storm"

bash "$ROOT/chaos/primitives/cache_flush.sh"
make load-spike CHAOS=1 || true

echo "[CHAOS] cache_stampede: complete"
