#!/usr/bin/env bash
# partial_inconsistency — brief Kafka pause during sustained load
# Expect: messaging gaps / transient errors (lab surrogate for publish path failure)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "=== Scenario: partial_inconsistency ==="
echo "Primitives: chaos/primitives/partial_failure.sh (short kafka pause)"
echo "Load: make load-concurrency (overlap with pause window)"
echo "Expected pattern: transient producer/consumer errors, possible inconsistency windows"

make load-concurrency &
LP=$!
sleep 15
PARTIAL_FAILURE_HOLD_SEC="${PARTIAL_FAILURE_HOLD_SEC:-6}" bash "$ROOT/chaos/primitives/partial_failure.sh" || true
wait "$LP" || true

echo "[CHAOS] partial_inconsistency: complete"
