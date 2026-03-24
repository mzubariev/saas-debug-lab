#!/usr/bin/env bash
# Run a named scenario from chaos/scenarios/<name>.sh
#
# Usage (from repo root):
#   ./chaos/runner.sh kafka_lag
#   make chaos-scenario SCENARIO=webhook_failure
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCENARIO="${1:-}"

if [[ -z "$SCENARIO" ]]; then
  echo "Usage: $0 <scenario_name>" >&2
  echo "Examples: $0 kafka_lag | webhook_failure | db_slowdown" >&2
  exit 1
fi

# Strip optional .sh suffix
SCENARIO="${SCENARIO%.sh}"

SCRIPT="$ROOT/chaos/scenarios/${SCENARIO}.sh"
if [[ ! -f "$SCRIPT" ]]; then
  echo "Unknown scenario: $SCENARIO (no file $SCRIPT)" >&2
  exit 1
fi

echo "[chaos] running scenario: $SCENARIO"
exec bash "$SCRIPT"
