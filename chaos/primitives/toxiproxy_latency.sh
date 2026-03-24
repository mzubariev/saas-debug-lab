#!/usr/bin/env bash
# Failure primitive: Add Latency on Toxiproxy path (mailhog-smtp proxy)
#
# Remove after: curl -sS -X DELETE "http://localhost:8474/proxies/mailhog-smtp/toxics/latency"
set -euo pipefail

TOXIPROXY="${TOXIPROXY_URL:-http://localhost:8474}"
LATENCY_MS="${TOXIC_LATENCY_MS:-2000}"

echo "[chaos] Adding latency toxic (${LATENCY_MS}ms) on mailhog-smtp"
curl -sS -X POST "${TOXIPROXY}/proxies/mailhog-smtp/toxics" \
  -H 'Content-Type: application/json' \
  -d "{\"name\":\"latency\",\"type\":\"latency\",\"attributes\":{\"latency\":${LATENCY_MS}}}"
echo
