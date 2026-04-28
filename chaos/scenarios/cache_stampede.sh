#!/usr/bin/env bash
# cache_stampede — cache_flush + spike_traffic
# Expect: High Latency, System Overload (cold cache + burst)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "=== Scenario: cache_stampede ==="
echo "Primitives: chaos/primitives/cache_flush.sh"
echo "Load: make load-spike"
echo "Expected pattern: High Latency, System Overload / cache miss storm"

bash "$ROOT/chaos/primitives/cache_flush.sh"
make load-spike

echo "[CHAOS] cache_stampede: complete"
