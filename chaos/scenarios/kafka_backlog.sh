#!/usr/bin/env bash
# kafka_backlog — slow_consumer + concurrency
# Expect: Kafka lag, delayed processing
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

cleanup() {
  if [[ -n "${SPID:-}" ]]; then
    kill "$SPID" 2>/dev/null || true
    wait "$SPID" 2>/dev/null || true
  fi
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

echo "=== Scenario: kafka_backlog ==="
echo "Primitives: chaos/primitives/slow_consumer.sh (CPU throttle on webhook-dispatcher)"
echo "Load: make load-concurrency CHAOS=1"
echo "Expected pattern: Kafka lag increasing, slow background processing"

SLOW_CONSUMER_DURATION_SEC="${SLOW_CONSUMER_DURATION_SEC:-300}" bash "$ROOT/chaos/primitives/slow_consumer.sh" &
SPID=$!

make load-concurrency CHAOS=1 || true

echo "[CHAOS] kafka_backlog: complete"
