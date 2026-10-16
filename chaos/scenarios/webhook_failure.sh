#!/usr/bin/env bash
# Scenario: External webhook endpoint failing (see docs/incidents-playbooks/DEBUGGING_SCENARIOS.md,
#   docs/incidents-playbooks/2_INCIDENT_PLAYBOOKS.md#3-webhooks-not-delivered--external-integration)
#
# Sends a single request to external-service-simulator with fail_rate=1.0 (that call always fails).
# For sustained high fail rate during load tests, restart external-service-simulator with
# WEBHOOK_SIMULATOR_DEFAULT_FAIL_RATE — see load-tests/README.md (retry_storm).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

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

URL="${WEBHOOK_SIM_URL:-http://localhost/external}/receive-webhook?fail_rate=1.0"

echo "=== Simulating webhook endpoint failure (single probe) ==="
echo "[chaos] POST $URL"
curl -sS -X POST "$URL" \
  -H 'Content-Type: application/json' \
  -d '{"event":"chaos.webhook_failure","data":{"source":"chaos/scenarios/webhook_failure.sh"}}' \
  | head -c 500
echo
