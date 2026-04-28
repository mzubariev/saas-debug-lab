#!/usr/bin/env bash
# Allocate a chunk of RAM inside the container for a short time (default ~120MB × 5s).
# Env: MEMORY_STRESS_CONTAINER (default task-service), MEMORY_STRESS_MB (default 120), MEMORY_STRESS_SECONDS (default 8)
set -euo pipefail

CONTAINER="${MEMORY_STRESS_CONTAINER:-task-service}"
MB="${MEMORY_STRESS_MB:-120}"
SECS="${MEMORY_STRESS_SECONDS:-8}"

echo "[CHAOS] Running memory_stress"
echo "[CHAOS] memory_stress: ~${MB}MB in ${CONTAINER} (bounded)"
docker exec "$CONTAINER" timeout "${SECS}s" python -c "import time; mb=int('${MB}'); x='z'*(mb*1024*1024); time.sleep(min(5, int('${SECS}')))" || true
echo "[CHAOS] memory_stress: finished"
