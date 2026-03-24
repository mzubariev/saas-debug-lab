#!/usr/bin/env bash
# Pick a random training scenario and run it (see docs/ROADMAP.md — Key rule:
# prefer scenarios / random over ad-hoc primitives).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SCENARIOS=(
  kafka_lag
  webhook_failure
  db_slowdown
)

RANDOM_INDEX=$((RANDOM % ${#SCENARIOS[@]}))
PICKED="${SCENARIOS[$RANDOM_INDEX]}"

echo "[chaos] random scenario: $PICKED"
exec bash "$DIR/runner.sh" "$PICKED"
