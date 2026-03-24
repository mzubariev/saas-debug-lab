#!/usr/bin/env bash
# Failure primitive: Kill Service (see docs/FAILURE_PRIMITIVES.md)
set -euo pipefail

SERVICE="${1:-}"
if [[ -z "$SERVICE" ]]; then
  echo "Usage: $0 <container_name>" >&2
  echo "Example: $0 webhook-dispatcher" >&2
  exit 1
fi

echo "[chaos] docker stop $SERVICE"
docker stop "$SERVICE"
