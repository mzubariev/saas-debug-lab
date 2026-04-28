#!/usr/bin/env bash
# CPU burn inside target container for a bounded time (default: task-service).
# Env: CPU_STRESS_CONTAINER (default task-service), CPU_STRESS_SECONDS (default 25)
set -euo pipefail

CONTAINER="${CPU_STRESS_CONTAINER:-task-service}"
SECS="${CPU_STRESS_SECONDS:-25}"

echo "[CHAOS] Running cpu_stress"
echo "[CHAOS] cpu_stress: ${CONTAINER} for ${SECS}s (busy loop)"
docker exec "$CONTAINER" timeout "${SECS}s" python -c 'exec("while True: pass")' || true
echo "[CHAOS] cpu_stress: finished"
