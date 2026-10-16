#!/usr/bin/env bash
# Scenario: Kafka lag / consumer backlog (see docs/incidents-playbooks/1_INCIDENT_PATTERNS.md#2-message-not-processed and playbooks § Kafka lag)
#
# Pauses webhook-dispatcher so consumers stop processing; traffic spike produces backlog.
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

echo "=== Simulating Kafka consumer stall + traffic spike ==="
echo "[chaos] docker pause webhook-dispatcher"
docker pause webhook-dispatcher

echo "[chaos] running load spike from repo root (blocks until k6 finishes)..."
make load-spike CHAOS=1 || true

echo ""
echo ">>> EXIT trap unpauses webhook-dispatcher."
echo ""
