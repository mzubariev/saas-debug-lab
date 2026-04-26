#!/usr/bin/env bash
# Failure primitive: Add Latency — downstream external-service-simulator (see docs/incidents-playbooks/4_FAILURE_PRIMITIVES.md#add-latency)
set -euo pipefail

DELAY="${DELAY_SECONDS:-2}"
URL="${WEBHOOK_SIM_URL:-http://localhost:8004}/receive-webhook?delay=${DELAY}"

echo "[chaos] POST $URL (chaos probe with delay=${DELAY}s)"
curl -sS -X POST "$URL" \
  -H 'Content-Type: application/json' \
  -d '{"event":"chaos.inject_latency","data":{"source":"chaos/primitives/inject_latency.sh"}}' \
  | head -c 500
echo
