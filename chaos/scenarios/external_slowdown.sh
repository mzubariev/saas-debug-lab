#!/usr/bin/env bash
# external_slowdown — slow outbound webhook simulator + concurrency
# Expect: high latency on downstream / webhook path
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "=== Scenario: external_slowdown ==="
echo "Primitives: chaos/primitives/inject_latency.sh (single delayed probe; use DELAY_SECONDS)"
echo "Load: make load-concurrency"
echo "Expected pattern: elevated tail latency when simulator responds slowly"

DELAY_SECONDS="${DELAY_SECONDS:-3}" bash "$ROOT/chaos/primitives/inject_latency.sh"
make load-concurrency

echo "[CHAOS] external_slowdown: complete (for sustained delay, raise DEFAULT_DELAY via simulator .env or query params in custom probes)"
