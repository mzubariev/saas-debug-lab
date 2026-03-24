#!/usr/bin/env bash
# Failure primitive: Slow Query Injection (Postgres pg_sleep)
#
# Env (optional, defaults match lab seed scripts):
#   POSTGRES_CONTAINER  default: postgres
#   POSTGRES_USER       default: admin
#   POSTGRES_DB         default: saas
#   SLEEP_SECONDS       default: 10
set -euo pipefail

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-postgres}"
POSTGRES_USER="${POSTGRES_USER:-admin}"
POSTGRES_DB="${POSTGRES_DB:-saas}"
SLEEP_SECONDS="${SLEEP_SECONDS:-10}"
if ! [[ "$SLEEP_SECONDS" =~ ^[0-9]+$ ]]; then
  echo "SLEEP_SECONDS must be a non-negative integer" >&2
  exit 1
fi

echo "[chaos] pg_sleep(${SLEEP_SECONDS}) on ${POSTGRES_CONTAINER} as ${POSTGRES_USER}/${POSTGRES_DB}"
docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 -c "SELECT pg_sleep(${SLEEP_SECONDS});"
