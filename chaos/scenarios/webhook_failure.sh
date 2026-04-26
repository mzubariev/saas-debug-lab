#!/usr/bin/env bash
# Scenario: External webhook endpoint failing (see docs/incidents-playbooks/DEBUGGING_SCENARIOS.md,
#   docs/incidents-playbooks/3_INCIDENT_PLAYBOOKS.md#3-webhooks-not-delivered--external-integration)
#
# Sends a single request to external-service-simulator with fail_rate=1.0 (that call always fails).
# For sustained high fail rate during load tests, restart external-service-simulator with
# WEBHOOK_SIMULATOR_DEFAULT_FAIL_RATE — see load-tests/README.md (retry_storm).
set -euo pipefail

URL="${WEBHOOK_SIM_URL:-http://localhost:8004}/receive-webhook?fail_rate=1.0"

echo "=== Simulating webhook endpoint failure (single probe) ==="
echo "[chaos] POST $URL"
curl -sS -X POST "$URL" \
  -H 'Content-Type: application/json' \
  -d '{"event":"chaos.webhook_failure","data":{"source":"chaos/scenarios/webhook_failure.sh"}}' \
  | head -c 500
echo
