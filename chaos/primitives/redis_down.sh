#!/usr/bin/env bash
# Failure primitive: cache / broker outage (Redis)
set -euo pipefail

echo "[chaos] stopping redis container"
docker stop redis
