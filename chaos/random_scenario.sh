#!/usr/bin/env bash
# Pick a random training scenario and run it (prefer scenarios over ad-hoc primitives).
# Scenarios list must stay in sync with chaos/scenarios/*.sh (see chaos/README.md).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SCENARIOS=(
  kafka_lag
  webhook_failure
  db_slowdown
  cache_stampede
  kafka_backlog
  consumer_down
  retry_storm
  duplicate_processing
  db_overload
  db_deadlock
  db_pool_exhaustion
  partial_inconsistency
  external_slowdown
)

RANDOM_INDEX=$((RANDOM % ${#SCENARIOS[@]}))
PICKED="${SCENARIOS[$RANDOM_INDEX]}"

echo "[chaos] random scenario selected: ${PICKED} (${#SCENARIOS[@]} total)"
exec bash "$DIR/runner.sh" "$PICKED"
