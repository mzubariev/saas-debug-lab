#!/usr/bin/env bash
# Failure primitive: restart / recovery (see docs/incidents-playbooks/4_FAILURE_PRIMITIVES.md#restart-loop)
set -euo pipefail

SERVICE="${1:-}"
if [[ -z "$SERVICE" ]]; then
  echo "Usage: $0 <container_name>" >&2
  exit 1
fi

echo "[chaos] docker restart $SERVICE"
docker restart "$SERVICE"
