# Load Tests — SaaS Debug Lab

k6-based load tests that exercise every layer of the stack: Nginx rate limiting,
Redis cache, Postgres connection pool, Kafka event throughput, and the webhook
retry pipeline. With **`core` + `observability`** up, you can correlate runs with
Prometheus (including **kafka-exporter** and **postgres-exporter** scrapes), Grafana,
and Jaeger as described in [`docs/system-architechture/ARCHITECTURE.md`](../docs/system-architechture/ARCHITECTURE.md).

---

## Prerequisites

**1. Install k6 1.7.1**

Scripts were checked with **k6 v1.7.1**. Image: `grafana/k6:1.7.1`.

```bash
# macOS
brew install k6
k6 version   # k6 v1.7.1

# Docker, from the repo root (the image must see lib/helpers.js)
docker run --rm --network host \
  -v "$PWD:/scripts" -w /scripts \
  grafana/k6:1.7.1 run load-tests/scripts/spike_traffic.js
```

**2. Start the stack**

```bash
cd infra
docker compose --profile core up -d

# (optional) start observability tools
docker compose --profile core --profile observability up -d
```

**3. Seed the database** (required for login; concurrency and slow_clients also read existing rows)

Postgres has no published host port, so `localhost:5432` from the host does not reach it. Run the seed on the Postgres network namespace (from the repo root):

```bash
docker run --rm --network container:postgres \
  -e DATABASE_URL=postgresql://admin:admin@127.0.0.1:5432/saas \
  -v "$PWD/scripts:/scripts" \
  python:3.14-slim \
  bash -c "pip install -q -r /scripts/requirements.txt && python /scripts/seed_dev.py"
```

---

## Quick Start

All scripts are run from the repository root. Every script accepts a `BASE_URL`
environment variable (default: `http://localhost`).

**Requests** carry `X-Request-ID` (see `requestId()` in `lib/helpers.js`) and k6 **tags**
`scenario` + `endpoint` on every call for dashboards and thresholds like
`http_req_duration{endpoint:create_task}`.

### Makefile (repo root)

```bash
make load-baseline      # baseline.js
make load-chaos         # chaos_mode.js
make load-spike         # spike_traffic.js
make load-retry-storm   # retry_storm.js
make load-concurrency   # concurrency.js
make load-slow-clients  # slow_clients.js
```

### Modes

**SLO** (default). `make load-baseline` with `CHAOS` unset. Thresholds stay in the script, including `abortOnFail` on the soak. A breached budget exits non-zero.

**Chaos** (observe only). `make load-baseline CHAOS=1`, or any `make load-* CHAOS=1`. k6 still prints metrics and the summary, and `options.thresholds` is cleared so a failure under injection does not abort the run. Chaos scenarios call the targets this way. Direct simulator calls default to `http://localhost/external` (host nginx). Set `WEBHOOK_SIM_URL=http://nginx/external` only when that Compose DNS name resolves.

### k6 CLI

```bash
# Run from the repo root
k6 run load-tests/scripts/spike_traffic.js
k6 run load-tests/scripts/concurrency.js
k6 run load-tests/scripts/retry_storm.js
k6 run load-tests/scripts/slow_clients.js
k6 run load-tests/scripts/baseline.js
k6 run load-tests/scripts/chaos_mode.js

# Long-running soak (overrides default duration in baseline.js)
k6 run --duration 12h load-tests/scripts/baseline.js

# Override base URL (e.g. remote host or inside Docker)
k6 run -e BASE_URL=http://my-server load-tests/scripts/concurrency.js

# Verbose VU/iteration logs (chaos_mode.js and any script you extend)
k6 run -e DEBUG_VU=1 load-tests/scripts/chaos_mode.js

# Stream live metrics to stdout while the test runs
k6 run --http-debug=full load-tests/scripts/spike_traffic.js 2>&1 | head -200
```

---

## Scenario Reference

### 0. `baseline.js` — Steady soak

**Run**
```bash
make load-baseline
# or long soak:
k6 run --duration 12h load-tests/scripts/baseline.js
```

Each VU keeps its own JWT (`getToken`, refresh when under 2 minutes remain; TTL is 30 minutes). Every created task is started and completed in that iteration. `GET /tasks` is not paginated, and cleanup deletes only completed tasks older than 5 minutes, so leaving rows in `created` would grow the list for the whole soak. Latency and `http_req_failed` thresholds use `abortOnFail` with `delayAbortEval: 1m`.

**Thresholds** — `create_task p(95)<1000`, `get_tasks p(95)<1500` (2026-10-16 clean-DB measurement, abort after 1m), `http_req_failed < 5%`, `checks > 99%`.

---

### 0b. `chaos_mode.js` — Retries + jitter

Creates a task; on non-201, waits 0–2s and retries the same title once. Tags: `scenario=chaos_mode`, `endpoint=create_task`.

```bash
make load-chaos
```

---

### 1. `spike_traffic.js` — Sudden traffic spike

**What it tests**
- Nginx `api` zone: **20 r/s**, **burst 100**, excess **delayed** (no `nodelay`), keyed by the `Authorization` header. One shared token from `setup()` is one bucket. Unauthenticated calls are not in this bucket.
- Arrival rate, not VU count: ~12 iterations/s (about 16 HTTP r/s, under the bucket), spike to ~46 iterations/s (about 60 HTTP r/s, 3×), then recover. Each iteration is one `GET /tasks` plus a 30% `POST /tasks`.
- 429 is an expected status (`expectedStatuses` includes 429) and is counted only in `rate_limited_requests`. Latency trends record 200/201 only.

**Traffic shape** (iteration starts per second)

```
iter/s 46 │                  ┌──────────────────────┐
          │          ramp ───┘                      └─── ramp down
       12 │  warmup ─┐                                        ┌─ recover
        0 ├──────────┴──────────────────────────────────────────────────
          0s        20s      35s                    95s       125s     185s
```

**Run**
```bash
k6 run load-tests/scripts/spike_traffic.js
```

**What to observe**

| Where | What to look for |
|---|---|
| k6 output | `rate_limited_requests` grows during the spike; `http_req_failed` stays low because 429 is expected |
| k6 output | `list_tasks_ms p95` drops as Redis cache warms up (first ~5 s cold, then <20 ms) |
| Kafka UI `localhost:8080` | `task_created` topic message rate mirrors POST /tasks volume |
| Jaeger `localhost:16686` | task-service span duration stays flat — spike absorbed by Nginx and Redis |
| MailHog `localhost:8025` | New emails arrive as task_created events reach notification-worker |

**Expected thresholds** — limiter invariant on successful (200/201) samples. The delay-queue cap is burst/rate = 5s; the budget is 5.3s:
- `http_req_failed rate < 5%` (429 does not count)
- `list_tasks_ms p95 < 5300 ms`
- `create_task_ms p95 < 5300 ms`
- `checks rate > 99%`
- `dropped_iterations count < 100`

---

### 2. `concurrency.js` — Sustained concurrent users

**What it tests**
- Steady-state latency under realistic mixed workload
- Full task lifecycle: `created → in_progress → completed`
- Redis cache-hit ratio stabilising during the 5-minute window
- Postgres connection pool stability under sustained writes
- Kafka consumer lag (webhook-dispatcher keeping up with task events)

**Traffic mix** (per VU iteration)

```
60% — GET /tasks              (list; Redis cache-aside, TTL 60 s)
20% — POST /tasks             (create; invalidates cache, emits Kafka event)
10% — Full lifecycle          (POST create → PATCH start → PATCH complete)
10% — GET /tasks/{id}         (point-read; single-task cache, TTL 120 s)
```

**Run**
```bash
k6 run load-tests/scripts/concurrency.js

# With 30 VUs (default 20):
k6 run -e VUS=30 load-tests/scripts/concurrency.js
```

**What to observe**

| Where | What to look for |
|---|---|
| k6 output | `read_ms p95 < 500 ms`, `write_ms p95 < 1500 ms` |
| k6 output | `cache_hint_likely rate` (proxy for Redis hit ratio) should rise above 70% within ~2 min |
| k6 output | `lifecycle_completed` vs `lifecycle_failed` — failures indicate state machine or DB issues |
| Redis Insight `localhost:5540` | `tasks:list` key TTL resets on every create; watch hit/miss counters |
| Kafka UI `localhost:8080` | Consumer group `webhook-dispatcher` lag should stay < 100 messages |
| Prometheus `localhost:9090` | `http_requests_total{job="task-service"}` rate, `http_request_duration_seconds` histogram |

**Expected thresholds** — test PASSES if:
- `http_req_failed rate < 5%`
- `read_ms p95 < 500 ms`, `p99 < 1000 ms`
- `write_ms p95 < 1500 ms`
- `lifecycle_failed count < 50`

---

### 3. `retry_storm.js` — Webhook failure cascade

**What it tests**
- webhook-dispatcher back-off: 3 attempts, sleeps about 1s then about 2s, jitter 0 to +10% (not ±10%, and no 4s sleep at the default `MAX_RETRIES`)
- Immediate DLQ routing on 4xx (no retries wasted on client errors)
- Dead-letter queue (`webhook_dlq` Kafka topic) filling under sustained failures
- Celery `retry_failed_webhooks` job draining the DLQ (runs every 60 s)
- Notification-worker receiving `task_created` events while the webhook storm runs
- Idempotency deduplication in external-service-simulator (already-processed keys return `duplicate`)

`FAIL_RATE` is only the `fail_rate` query param on **direct** simulator calls (`simulator_baseline`). It does not control webhook-dispatcher. Dispatcher posts use the simulator process `DEFAULT_FAIL_RATE`. The `duplicate_key` scenario sends the same `Idempotency-Key` twice with `fail_rate=0` and expects body status `duplicate`.

**Setup — configure webhook failures before running**

Option A: restart external-service-simulator with a high default fail rate:
```bash
DEFAULT_FAIL_RATE=0.9 \
docker compose -f infra/docker-compose.yml up -d --no-deps external-service-simulator
```

A Toxiproxy toxic on `mailhog-smtp` slows notification email only. It does not change webhook delivery or the API.

**Scenarios**

```
organic_task_events  5 VUs × 3 min  → POST /tasks → task_created Kafka event
                                       → webhook-dispatcher → simulator (DEFAULT_FAIL_RATE)
simulator_baseline   2 VUs × 3 min  → direct POST /receive-webhook?fail_rate=FAIL_RATE
duplicate_key        1 VU  × 3 min  → same Idempotency-Key twice, second status "duplicate"
```

> Outbound dispatch is triggered exclusively via Kafka events. The organic task flow
> already exercises the full retry pipeline end-to-end.

**Run**
```bash
k6 run -e FAIL_RATE=0.9 load-tests/scripts/retry_storm.js
```

**What to observe**

| Where | What to look for |
|---|---|
| Kafka UI `localhost:8080` | `webhook_dlq` topic depth growing during test, draining in 60-s windows (Celery retries) |
| scheduler-worker logs | `retry_failed_webhooks` (there is no Flower service in this compose file) |
| webhook-dispatcher logs | `webhook_attempt_failed` (with `retry=False` for 4xx), `webhook_failed_permanently`, DLQ structlog events |
| k6 output | `tasks_created_for_events` counter vs `simulator_fail_rate` (~0.9) |
| Jaeger `localhost:16686` | Traces: api-gateway → task-service → Kafka → webhook-dispatcher → external-service-simulator |

---

### 4. `slow_clients.js` — Long-held connections

**What it tests**
- Connection pool exhaustion under many idle keep-alive connections
- Think time is `sleep()` after the response. It does not hold the upstream request, so it does not arm nginx `proxy_read_timeout` (30s) or the gateway timeout (5s)
- Postgres idle connection accumulation (`pg_stat_activity`)
- Graceful degradation: normal requests must still succeed while slow clients hold connections

**Three concurrent user types**

```
normal_reader   10 VUs  1-3 s  think  → baseline; must stay healthy throughout
slow_browser    30 VUs  8-20 s think  → holds keep-alive connections; connection pool pressure
heavy_reader    10 VUs  25-35 s think → long pause between requests; does not by itself return 504
```

**Run**
```bash
k6 run load-tests/scripts/slow_clients.js
```

**To trigger actual 504s** (optional): add >30 s upstream latency via Toxiproxy.
First, add a proxy from Toxiproxy to api-gateway (not configured by default), then:
```bash
curl -X POST http://localhost:8474/proxies \
  -H 'Content-Type: application/json' \
  -d '{"name":"api-gw","listen":"0.0.0.0:18000","upstream":"api-gateway:8000","enabled":true}'

curl -X POST http://localhost:8474/proxies/api-gw/toxics \
  -H 'Content-Type: application/json' \
  -d '{"name":"slow","type":"latency","attributes":{"latency":35000}}'
```
Point `BASE_URL=http://localhost:18000` to route through the toxic proxy:
```bash
k6 run -e BASE_URL=http://localhost:18000 load-tests/scripts/slow_clients.js
```

**What to observe**

| Where | What to look for |
|---|---|
| k6 output | `normal_reader_ok count` stays above 50 even as slow clients pile up |
| k6 output | `nginx_504_timeouts` — increases only when Toxiproxy latency is active |
| Nginx logs | `docker logs nginx --follow` — upstream timed out, 504 |
| Postgres | `docker exec postgres psql -U admin saas -c "SELECT state, count(*) FROM pg_stat_activity GROUP BY state;"` |
| Prometheus | `pg_connections_by_state_count{state="idle"}` (postgres-exporter custom query) creeping up under slow browser load |
| k6 output | `think_time_ms` trend (distribution of think times) |

**Expected thresholds** — test PASSES if:
- `normal_reader_ok count > 50`
- `http_req_failed rate < 15%`
- `nginx_504_timeouts count < 100`

---

## Configuration Reference

| Environment variable | Default | Description |
|---|---|---|
| `BASE_URL` | `http://localhost` | Nginx entry point for all API calls |
| `WEBHOOK_SIM_URL` | `http://localhost/external` | Simulator through host nginx. `http://nginx/external` only if you set this env (Compose DNS) |
| `CHAOS` | unset | `1` clears thresholds (observe only). Unset keeps SLO thresholds and `abortOnFail` |
| `VUS` | `20` | VU count override for `concurrency.js` |
| `FAIL_RATE` | `0.9` | Query `fail_rate` on direct simulator calls only. Dispatcher uses `DEFAULT_FAIL_RATE` |
| `DEBUG_VU` | unset | Set to `1` to print `VU` / `ITER` in `chaos_mode.js` |

---

## Useful Commands During Tests

```bash
# Live k6 metrics in a second terminal
k6 run --out json=results.json load-tests/scripts/concurrency.js
# then:
cat results.json | jq '.metric | select(.type == "Trend") | .name, .values'

# Watch Nginx access log
docker logs nginx --follow 2>&1 | grep -E '429|504|499'

# Watch task-service structured logs
docker logs task-service --follow | python3 -m json.tool 2>/dev/null | grep -E 'event|duration'

# Postgres active connection count (run in a loop)
watch -n2 "docker exec postgres psql -U admin saas -tAc \
  \"SELECT state, count(*) FROM pg_stat_activity GROUP BY state\""

# Kafka DLQ depth
docker exec kafka kafka-run-class.sh kafka.tools.GetOffsetShell \
  --bootstrap-server localhost:9092 --topic webhook_dlq --time -1

# Redis cache key TTL
docker exec redis redis-cli TTL tasks:list
```

---

## Prometheus Queries

Paste these into `http://localhost:9090/graph` while a test is running:

```promql
# Request rate per service
rate(http_requests_total[1m])

# P95 response time (task-service)
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{job="task-service"}[1m]))

# Error rate
rate(http_requests_total{status=~"5.."}[1m]) / rate(http_requests_total[1m])

# Rate-limited requests (Nginx)
rate(nginx_http_requests_total{status="429"}[30s])
```

---

## Thresholds

`baseline.js` is the latency SLO: `create_task` p95 under 1000 ms and `get_tasks` p95 under 1500 ms, with `http_req_failed` under 5% and `checks` above 99%. Those budgets abort the soak after 1 minute.

`spike_traffic.js` asserts the nginx limiter invariant, not that latency SLO. One shared token is one 20 r/s bucket with burst 100 and no `nodelay`, so excess requests wait at most burst/rate = 5s. Successful samples (`list_tasks_ms`, `create_task_ms`) must stay under 5300 ms. `http_req_failed` stays under 5% (429 is expected and is not a failure) and `checks` stay above 99%, so the spike must not produce 5xx. `dropped_iterations` stays under 100.

`CHAOS=1` still clears every threshold. `concurrency.js` still carries older 500/800 ms placeholders.

### Measured baseline

2026-10-16, clean database, k6 1.7.1, nginx on port 80.

| Run | Result |
| --- | --- |
| `baseline.js`, 20 VUs, 1h | `create_task` p95 520 ms, `get_tasks` p95 750 ms, 0% failed |
| `spike_traffic.js`, peak about 3× the nginx limit | p95 5.01 s on both `list_tasks_ms` and `create_task_ms` (the 5s queue cap), 0 failed, 0 non-2xx besides 429 |

---

## Project Layout

```
load-tests/
├── README.md                  ← this file
├── lib/
│   └── helpers.js             ← login, requestId, reqTags, auth/anon headers, HTTP wrappers
└── scripts/
    ├── baseline.js            ← steady / long soak (12h via --duration)
    ├── chaos_mode.js          ← retry the same title once; chaos training
    ├── spike_traffic.js       ← sudden spike, Nginx rate limit, cache warm-up
    ├── concurrency.js         ← steady-state mixed workload, full lifecycle
    ├── retry_storm.js         ← webhook failures, DLQ, Celery retries
    └── slow_clients.js        ← connection pool exhaustion, proxy timeouts
```

Repo root `Makefile` exposes `make load-*` targets for the scripts above.

Chaos engineering (pause services, DB sleep, random scenarios) lives in **`chaos/`** — see `chaos/README.md` and `make chaos-random`.
