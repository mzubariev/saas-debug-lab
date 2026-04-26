# Chaos engineering (lab)

Small **primitives** (atomic faults) and **scenarios** (composed flows) for observability training.  
Aligned with [Failure primitives](../docs/incidents-playbooks/4_FAILURE_PRIMITIVES.md), [Incident patterns](../docs/incidents-playbooks/2_INCIDENT_PATTERNS.md), and [Debugging scenarios](../docs/incidents-playbooks/DEBUGGING_SCENARIOS.md).

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


## Usage

```bash
# From repository root
./chaos/runner.sh kafka_lag
./chaos/runner.sh webhook_failure
./chaos/runner.sh db_slowdown

make chaos-random
make chaos-scenario SCENARIO=db_slowdown
```

### After `kafka_lag`

```bash
docker unpause webhook-dispatcher
```

### After `toxiproxy_latency` primitive

```bash
curl -sS -X DELETE "http://localhost:8474/proxies/mailhog-smtp/toxics/latency"
```

## Primitives reference


| Script                 | FAILURE_PRIMITIVES concept               |
| ---------------------- | ---------------------------------------- |
| `kill_service.sh`      | Kill Service                             |
| `restart_service.sh`   | Recovery / restart                       |
| `kafka_down.sh`        | Messaging / dependency down              |
| `redis_down.sh`        | Cache down                               |
| `slow_db.sh`           | Slow Query Injection                     |
| `inject_latency.sh`    | Add Latency (external-service-simulator) |
| `toxiproxy_latency.sh` | Add Latency (SMTP proxy path)            |


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


## Workflow (from ROADMAP)

1. Start stack: `docker compose --profile core up -d` (under `infra/`).
2. Optional baseline load: `make load-baseline`.
3. Trigger chaos: `make chaos-random`.
4. Observe Grafana / Kibana / Jaeger / Kafka UI as in `[docs/incidents-playbooks/DEBUGGING_SCENARIOS.md](../docs/incidents-playbooks/DEBUGGING_SCENARIOS.md)`.

