#!/usr/bin/env bash
# Flush Redis (FLUSHALL). Lab-only — clears all DB indexes on shared Redis.
set -euo pipefail

CONTAINER="${REDIS_CONTAINER:-redis}"

echo "[CHAOS] Running cache_flush"
echo "[CHAOS] cache_flush: FLUSHALL on ${CONTAINER}"
docker exec "$CONTAINER" redis-cli INFO keyspace | head -20 || true
docker exec "$CONTAINER" redis-cli FLUSHALL
echo "[CHAOS] cache_flush: done (all Redis keys removed)"
