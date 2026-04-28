#!/usr/bin/env bash
# kafka_backlog — slow_consumer + concurrency
# Expect: Kafka lag, delayed processing
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "=== Scenario: kafka_backlog ==="
echo "Primitives: chaos/primitives/slow_consumer.sh (CPU throttle on webhook-dispatcher)"
echo "Load: make load-concurrency"
echo "Expected pattern: Kafka lag increasing, slow background processing"

SLOW_CONSUMER_DURATION_SEC="${SLOW_CONSUMER_DURATION_SEC:-300}" bash "$ROOT/chaos/primitives/slow_consumer.sh" &
SPID=$!

cleanup() {
  kill "$SPID" 2>/dev/null || true
  wait "$SPID" 2>/dev/null || true
}
trap cleanup EXIT

make load-concurrency
cleanup
trap - EXIT

echo "[CHAOS] kafka_backlog: complete"
