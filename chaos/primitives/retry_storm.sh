#!/usr/bin/env bash
# Raise external-service-simulator default fail rate (recreates container from infra compose).
# Env: RETRY_STORM_FAIL_RATE (default 0.92). Restore: EXTERNAL_SIMULATOR_DEFAULT_FAIL_RATE=0 docker compose … recreate
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RATE="${RETRY_STORM_FAIL_RATE:-0.92}"

echo "[CHAOS] Running retry_storm"
echo "[CHAOS] retry_storm: EXTERNAL_SIMULATOR_DEFAULT_FAIL_RATE=${RATE} (recreate simulator via infra compose)"
cd "$ROOT/infra"
EXTERNAL_SIMULATOR_DEFAULT_FAIL_RATE="$RATE" docker compose --profile core up -d --no-deps --force-recreate external-service-simulator
echo "[CHAOS] retry_storm: simulator recreated. Restore baseline:"
echo "  cd infra && EXTERNAL_SIMULATOR_DEFAULT_FAIL_RATE=0 docker compose --profile core up -d --no-deps --force-recreate external-service-simulator"
