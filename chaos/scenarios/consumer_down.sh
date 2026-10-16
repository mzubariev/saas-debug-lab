#!/usr/bin/env bash
# consumer_down — stop_consumer + concurrency
# Expect: lag increase, background processing stopped
# Recovery runs from the EXIT trap even when k6 fails.
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

echo "=== Scenario: consumer_down ==="
echo "Primitives: chaos/primitives/stop_consumer.sh (docker pause webhook-dispatcher)"
echo "Load: make load-concurrency CHAOS=1"
echo "Expected pattern: Kafka backlog, no webhook delivery until unpause"

bash "$ROOT/chaos/primitives/stop_consumer.sh"
make load-concurrency CHAOS=1 || true

echo ""
echo ">>> EXIT trap unpauses webhook-dispatcher."
echo ""
