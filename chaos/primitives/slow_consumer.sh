#!/usr/bin/env bash
# Throttle consumer CPU to simulate slow processing (reversible via docker update).
# Env: KAFKA_CONSUMER_SERVICE (default webhook-dispatcher), SLOW_CONSUMER_CPUS (default 0.08),
#      SLOW_CONSUMER_DURATION_SEC (default 60), RESTORE_CPUS (default 4.0)
set -euo pipefail

SERVICE="${KAFKA_CONSUMER_SERVICE:-webhook-dispatcher}"
CPUS="${SLOW_CONSUMER_CPUS:-0.08}"
DURATION="${SLOW_CONSUMER_DURATION_SEC:-60}"
RESTORE="${RESTORE_CPUS:-4.0}"

echo "[CHAOS] Running slow_consumer"

restore() {
  echo "[CHAOS] slow_consumer: restoring CPU quota for ${SERVICE}"
  docker update --cpus="$RESTORE" "$SERVICE" 2>/dev/null || docker update --cpus=0 "$SERVICE" 2>/dev/null || true
}
trap restore EXIT

echo "[CHAOS] slow_consumer: docker update --cpus=${CPUS} ${SERVICE} for ${DURATION}s"
docker update --cpus="$CPUS" "$SERVICE"
sleep "$DURATION"
# trap runs restore
