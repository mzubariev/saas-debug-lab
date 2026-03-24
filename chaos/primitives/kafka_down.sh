#!/usr/bin/env bash
# Failure primitive: dependency / messaging outage (Kafka)
set -euo pipefail

echo "[chaos] stopping kafka container"
docker stop kafka
