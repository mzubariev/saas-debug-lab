#!/usr/bin/env bash
# Scenario: Slow DB / API latency (see docs/incidents-playbooks/3_INCIDENT_PLAYBOOKS.md#1-high-api-latency)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "=== Simulating slow database (pg_sleep via primitive) ==="
bash "$ROOT/chaos/primitives/slow_db.sh"
