#!/usr/bin/env bash
# external_slowdown — slow outbound webhook simulator + concurrency
# Expect: high latency on downstream / webhook path
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

echo "=== Scenario: external_slowdown ==="
echo "Primitives: chaos/primitives/inject_latency.sh (single delayed probe; use DELAY_SECONDS)"
echo "Load: make load-concurrency CHAOS=1"
echo "Expected pattern: elevated tail latency when simulator responds slowly"

DELAY_SECONDS="${DELAY_SECONDS:-3}" bash "$ROOT/chaos/primitives/inject_latency.sh"
make load-concurrency CHAOS=1 || true

echo "[CHAOS] external_slowdown: complete (for sustained delay, raise DEFAULT_DELAY via simulator .env or query params in custom probes)"
