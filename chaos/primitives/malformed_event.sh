#!/usr/bin/env bash
# Send invalid JSON to a Kafka topic (default task_created) to exercise consumer error paths.
set -euo pipefail

TOPIC="${KAFKA_TOPIC:-task_created}"

echo "[CHAOS] Running malformed_event"
echo "[CHAOS] malformed_event: broken JSON → ${TOPIC}"
printf '{ this is not valid json' | docker exec -i kafka kafka-console-producer --bootstrap-server kafka:9092 --topic "$TOPIC" >/dev/null || true
echo "[CHAOS] malformed_event: done"
