#!/usr/bin/env bash
# Scenario: Kafka lag / consumer backlog (see docs/incidents-playbooks/1_INCIDENT_PATTERNS.md#2-message-not-processed and playbooks § Kafka lag)
#
# Pauses webhook-dispatcher so consumers stop processing; traffic spike produces backlog.
#
# Recovery (required after this script):
#   docker unpause webhook-dispatcher
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "=== Simulating Kafka consumer stall + traffic spike ==="
echo "[chaos] docker pause webhook-dispatcher"
docker pause webhook-dispatcher

echo "[chaos] running load spike from repo root (blocks until k6 finishes)..."
make load-spike

echo ""
echo ">>> webhook-dispatcher is still PAUSED. Resume with:"
echo "    docker unpause webhook-dispatcher"
echo ""
