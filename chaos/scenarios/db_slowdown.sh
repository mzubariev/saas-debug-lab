#!/usr/bin/env bash
# Scenario: Slow DB / API latency (maps to docs/SCENARIO_MAPPING.md — High API latency)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "=== Simulating slow database (pg_sleep via primitive) ==="
bash "$ROOT/chaos/primitives/slow_db.sh"
