#!/usr/bin/env bash
# consumer_down — stop_consumer + concurrency
# Expect: lag increase, background processing stopped
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "=== Scenario: consumer_down ==="
echo "Primitives: chaos/primitives/stop_consumer.sh (docker pause webhook-dispatcher)"
echo "Load: make load-concurrency"
echo "Expected pattern: Kafka backlog, no webhook delivery until unpause"

bash "$ROOT/chaos/primitives/stop_consumer.sh"
make load-concurrency

echo ""
echo ">>> webhook-dispatcher is still PAUSED. Resume with:"
echo "    docker unpause webhook-dispatcher"
echo ""
