#!/usr/bin/env bash
# Simulates publish path blip: briefly pause Kafka so producers/consumers stall (reversible).
# Not a true "DB committed without event" — lab-safe surrogate for messaging outage mid-flight.
# Env: PARTIAL_FAILURE_HOLD_SEC (default 4)
set -euo pipefail

HOLD="${PARTIAL_FAILURE_HOLD_SEC:-4}"

echo "[CHAOS] Running partial_failure"
echo "[CHAOS] partial_failure: docker pause kafka for ${HOLD}s"
docker pause kafka
sleep "$HOLD"
docker unpause kafka
echo "[CHAOS] partial_failure: kafka unpaused"
