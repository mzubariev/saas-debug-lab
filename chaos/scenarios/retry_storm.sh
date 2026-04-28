#!/usr/bin/env bash
# retry_storm — high simulator fail rate + retry_storm.js
# Expect: overload, duplicate processing / DLQ churn
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "=== Scenario: retry_storm ==="
echo "Primitives: chaos/primitives/retry_storm.sh"
echo "Load: make load-retry-storm"
echo "Expected pattern: retry storm, DLQ growth, Celery replay pressure"

bash "$ROOT/chaos/primitives/retry_storm.sh"
make load-retry-storm

echo "[CHAOS] retry_storm: load finished. Restore simulator fail rate if needed:"
echo "  cd infra && EXTERNAL_SIMULATOR_DEFAULT_FAIL_RATE=0 docker compose --profile core up -d --no-deps --force-recreate external-service-simulator"
