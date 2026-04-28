#!/usr/bin/env bash
# db_deadlock — long row lock + concurrency
# Expect: blocked queries, latency spikes
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "=== Scenario: db_deadlock ==="
echo "Primitives: chaos/primitives/db_lock.sh (FOR UPDATE + pg_sleep)"
echo "Load: make load-concurrency"
echo "Expected pattern: task updates blocked, elevated latency"

CHAOS_DB_LOCK_SECONDS="${CHAOS_DB_LOCK_SECONDS:-120}" bash "$ROOT/chaos/primitives/db_lock.sh"
sleep 2
make load-concurrency

echo "[CHAOS] db_deadlock: wait for lock session to finish or terminate long psql sleeps on postgres."
echo "  docker exec postgres psql -U admin -d saas -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'active' AND query LIKE '%FOR UPDATE%';\""
