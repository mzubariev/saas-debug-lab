-- Runs once when the PostgreSQL data directory is first initialised.
-- Creates pg_stat_statements so the postgres-exporter can expose per-query
-- latency percentiles from the very first container start.
--
-- EXISTING INSTALLATIONS: if you already have a postgres volume this script
-- will NOT re-run.  Apply manually with:
--   docker exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB \
--     -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;"
--   docker exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB \
--     -c "SELECT pg_stat_statements_reset();"

CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
