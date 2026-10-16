#!/usr/bin/env bash
# partial_inconsistency — brief Kafka pause during sustained load
# Expect: messaging gaps / transient errors (lab surrogate for publish path failure)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

cleanup() {
  if [[ -n "${LP:-}" ]]; then
    wait "$LP" 2>/dev/null || true
  fi
  docker unpause kafka 2>/dev/null || true
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

echo "=== Scenario: partial_inconsistency ==="
echo "Primitives: chaos/primitives/partial_failure.sh (short kafka pause)"
echo "Load: make load-concurrency CHAOS=1 (overlap with pause window)"
echo "Expected pattern: transient producer/consumer errors, possible inconsistency windows"

make load-concurrency CHAOS=1 &
LP=$!
sleep 15
PARTIAL_FAILURE_HOLD_SEC="${PARTIAL_FAILURE_HOLD_SEC:-6}" bash "$ROOT/chaos/primitives/partial_failure.sh" || true
wait "$LP" || true

echo "[CHAOS] partial_inconsistency: complete"
