#!/usr/bin/env bash
# Pause a Kafka consumer container (default: webhook-dispatcher). Reversible with docker unpause.
set -euo pipefail

SERVICE="${KAFKA_CONSUMER_SERVICE:-webhook-dispatcher}"

echo "[CHAOS] Running stop_consumer"
echo "[CHAOS] stop_consumer: docker pause ${SERVICE}"
docker pause "$SERVICE"
echo "[CHAOS] stop_consumer: ${SERVICE} is PAUSED — resume with: docker unpause ${SERVICE}"
