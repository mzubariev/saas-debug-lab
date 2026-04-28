#!/usr/bin/env bash
# duplicate_processing — duplicate_events + retry_storm.js
# Expect: duplicate data / idempotency stress
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "=== Scenario: duplicate_processing ==="
echo "Primitives: chaos/primitives/duplicate_events.sh"
echo "Load: make load-retry-storm"
echo "Expected pattern: duplicate Kafka deliveries, idempotency-key behaviour"

bash "$ROOT/chaos/primitives/duplicate_events.sh"
make load-retry-storm

echo "[CHAOS] duplicate_processing: complete"
