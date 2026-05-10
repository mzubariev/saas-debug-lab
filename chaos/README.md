# Chaos engineering (lab)

Small **primitives** (atomic faults) and **scenarios** (composed flows) for observability training.  
Aligned with [Failure primitives](../docs/incidents-playbooks/PROD_INCIDENTS.md), [Incident patterns](../docs/incidents-playbooks/1_INCIDENT_PATTERNS.md), and [Debugging scenarios](../docs/incidents-playbooks/DEBUGGING_SCENARIOS.md).

## Rules

1. **Prefer scenarios** (`runner.sh`, `random_scenario.sh`, `make chaos-scenario`) over running primitives directly during exercises.
2. **Recover** after each run (unpause containers, restart services, remove toxics) — scripts print hints where needed.
3. Run from a host with **Docker** and (for spike scenario) **k6** on `PATH`.

## Layout


| Path                       | Role                            |
| -------------------------- | ------------------------------- |
| `chaos/primitives/`        | One script = one atomic failure |
| `chaos/scenarios/`         | Composed incidents              |
| `chaos/runner.sh`          | `runner.sh <scenario>`          |
| `chaos/random_scenario.sh` | Random training scenario        |


## Scenarios → docs mapping


| Scenario          | docs/incidents-playbooks/ (patterns + scenarios)     | Primitives used                                                      |
| ----------------- | ---------------------------------------------------- | -------------------------------------------------------------------- |
| `kafka_lag`       | Kafka lag increasing / Background processing stopped | Stop Consumer (pause dispatcher) + Traffic Spike (`make load-spike`) |
| `webhook_failure` | Tasks created but webhooks not delivered             | External API Failure (simulator `fail_rate=1.0` on one request)      |
| `db_slowdown`     | High API latency                                     | Slow Query Injection (`pg_sleep`)                                    |
| `cache_stampede`  | Cold cache + burst                                   | `cache_flush.sh` + `make load-spike`                                  |
| `kafka_backlog`   | Slow consumer / lag                                  | `slow_consumer.sh` + `make load-concurrency`                            |
| `consumer_down`   | Consumer stopped                                     | `stop_consumer.sh` + `make load-concurrency`                         |
| `retry_storm`     | Webhook retry / DLQ pressure                         | `retry_storm.sh` + `make load-retry-storm`                           |
| `duplicate_processing` | Duplicate deliveries                            | `duplicate_events.sh` + `make load-retry-storm`                       |
| `db_overload`     | DB slow path                                         | `slow_db.sh` + `make load-concurrency`                                 |
| `db_deadlock`     | Row lock contention                                  | `db_lock.sh` + `make load-concurrency`                                |
| `db_pool_exhaustion` | Connection exhaustion                             | `db_pool_exhaust.sh` + `make load-concurrency` (auto cleanup SQL)     |
| `partial_inconsistency` | Messaging blip during load                     | `partial_failure.sh` + overlapping `make load-concurrency`            |
| `external_slowdown` | Downstream latency                               | `inject_latency.sh` + `make load-concurrency`                          |


## Usage

```bash
# From repository root
./chaos/runner.sh kafka_lag
./chaos/runner.sh cache_stampede
./chaos/runner.sh retry_storm

make kafka-backlog
make cache-stampede
make retry-storm
make chaos-random
make chaos-scenario SCENARIO=db_slowdown
```

### After `kafka_lag` or `consumer_down` or `kafka_backlog` (pause / throttle)

```bash
docker unpause webhook-dispatcher
# If slow_consumer ran CPU throttle:
docker update --cpus=4.0 webhook-dispatcher 2>/dev/null || true
```

### After `retry_storm` primitive / scenario (high simulator fail rate)

```bash
cd infra && EXTERNAL_SIMULATOR_DEFAULT_FAIL_RATE=0 docker compose --profile core up -d --no-deps --force-recreate external-service-simulator
```

(`infra/docker-compose.yml` wires `DEFAULT_FAIL_RATE` from host `EXTERNAL_SIMULATOR_DEFAULT_FAIL_RATE` for this lab.)

### After `toxiproxy_latency` primitive

```bash
curl -sS -X DELETE "http://localhost:8474/proxies/mailhog-smtp/toxics/latency"
```

## Primitives reference


| Script                 | PROD_INCIDENTS concept               |
| ---------------------- | ---------------------------------------- |
| `kill_service.sh`      | Kill Service                             |
| `restart_service.sh`   | Recovery / restart                       |
| `kafka_down.sh`        | Messaging / dependency down              |
| `redis_down.sh`        | Cache down                               |
| `slow_db.sh`           | Slow Query Injection                     |
| `inject_latency.sh`    | Add Latency (external-service-simulator) |
| `toxiproxy_latency.sh` | Add Latency (SMTP proxy path)            |
| `stop_consumer.sh`     | Pause Kafka consumer (`webhook-dispatcher` by default) |
| `slow_consumer.sh`     | CPU-throttle consumer (`docker update --cpus`)           |
| `cache_flush.sh`       | Redis `FLUSHALL`                                         |
| `cpu_stress.sh`        | CPU burn inside container (default `task-service`)       |
| `memory_stress.sh`     | Short RAM spike inside container                         |
| `retry_storm.sh`       | Recreate simulator with high `DEFAULT_FAIL_RATE`         |
| `duplicate_events.sh`  | Duplicate `task_created` Kafka payloads                  |
| `malformed_event.sh`   | Invalid JSON to Kafka topic                              |
| `db_lock.sh`           | Long `FOR UPDATE` + `pg_sleep` session                   |
| `db_pool_exhaust.sh`   | Many concurrent `pg_sleep` DB sessions                   |
| `partial_failure.sh`   | Brief `docker pause kafka` / unpause                     |


### `slow_db.sh` environment

Matches `infra/.env` Postgres settings if exported:

- `POSTGRES_USER` (default `admin`)
- `POSTGRES_DB` (default `saas`)
- `POSTGRES_CONTAINER` (default `postgres`)
- `SLEEP_SECONDS` (default `10`)

## Makefile targets


| Target                              | Action                            |
| ----------------------------------- | --------------------------------- |
| `make chaos-scenario SCENARIO=name` | Run `chaos/scenarios/name.sh`     |
| `make chaos-random`                 | Random scenario                   |
| `make break-kafka`                  | `docker stop kafka`               |
| `make break-redis`                  | `docker stop redis`               |
| `make slow-db`                      | `slow_db.sh`                      |
| `make kill-worker`                  | `docker stop notification-worker` |
| `make cache-stampede`               | `chaos/scenarios/cache_stampede.sh` |
| `make kafka-backlog`                | `chaos/scenarios/kafka_backlog.sh`  |
| `make retry-storm`                  | `chaos/scenarios/retry_storm.sh`    |


## Workflow (from ROADMAP)

1. Start stack: `docker compose --profile core up -d` (under `infra/`).
2. Optional baseline load: `make load-baseline`.
3. Trigger chaos: `make chaos-random`.
4. Observe Grafana / Kibana / Jaeger / Kafka UI as in `[docs/incidents-playbooks/DEBUGGING_SCENARIOS.md](../docs/incidents-playbooks/DEBUGGING_SCENARIOS.md)`.

