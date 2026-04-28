#!/usr/bin/env bash
# db_overload — slow_db + concurrency
# Expect: high API latency
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "=== Scenario: db_overload ==="
echo "Primitives: chaos/primitives/slow_db.sh"
echo "Load: make load-concurrency"
echo "Expected pattern: High API latency (Postgres pg_sleep)"

bash "$ROOT/chaos/primitives/slow_db.sh"
make load-concurrency

echo "[CHAOS] db_overload: complete"
