# Load Tests — SaaS Debug Lab

k6-based load tests that exercise every layer of the stack: Nginx rate limiting,
Redis cache, Postgres connection pool, Kafka event throughput, and the webhook
retry pipeline.

---

## Prerequisites

**1. Install k6**

```bash
# macOS
brew install k6

# Linux
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
  | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6

# Docker (no install needed)
docker run --rm -i --network host grafana/k6 run - < load-tests/scripts/spike_traffic.js
```

**2. Start the stack**

```bash
cd infra
docker compose --profile core up -d

# (optional) start observability tools
docker compose --profile core --profile observability up -d
```

**3. Seed the database** (required for concurrency and slow_clients tests)

```bash
pip install -r scripts/requirements.txt
DATABASE_URL=postgresql://admin:admin@localhost:5432/saas python scripts/seed_dev.py
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

**Thresholds** — `http_req_duration` by `endpoint:create_task` / `get_tasks`, `http_req_failed < 5%`.

---

### 0b. `chaos_mode.js` — Retries + jitter

Creates a task; on non-201, waits 0–2s and retries once. Tags: `scenario=chaos_mode`, `endpoint=create_task`.

```bash
make load-chaos
```

---

### 1. `spike_traffic.js` — Sudden traffic spike

**What it tests**
- Nginx rate limiting (`zone=api`: 10 req/s burst 20 per IP)
- Redis `tasks:list` cache warming under burst reads
- Kafka producer throughput as write volume spikes
- System behaviour when traffic drops suddenly (recovery)

**Traffic shape**

```
VUs  150 │                  ┌──────────────────────┐
         │          ramp ───┘                      └─── ramp down
      10 │  warmup ─┐                                        ┌─ cool-down
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
| k6 output | `rate_limited_requests` counter grows rapidly; `http_req_failed` rate ≈ 30-40% during spike |
| k6 output | `list_tasks_ms p95` drops as Redis cache warms up (first ~5 s cold, then <20 ms) |
| Kafka UI `localhost:8080` | `task_created` topic message rate mirrors POST /tasks volume |
| Jaeger `localhost:16686` | task-service span duration stays flat — spike absorbed by Nginx and Redis |
| MailHog `localhost:8025` | New emails arrive as task_created events reach notification-worker |

**Expected thresholds** — test PASSES if:
- `http_req_failed rate < 40%`
- `list_tasks_ms p95 < 800 ms`
- `create_task_ms p95 < 1500 ms`

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
| Prometheus `localhost:9090` | `http_requests_total{service="task-service"}` rate, `http_request_duration_seconds` histogram |

**Expected thresholds** — test PASSES if:
- `http_req_failed rate < 5%`
- `read_ms p95 < 500 ms`, `p99 < 1000 ms`
- `write_ms p95 < 1500 ms`
- `lifecycle_failed count < 50`

---

### 3. `retry_storm.js` — Webhook failure cascade

**What it tests**
- webhook-dispatcher exponential back-off (1 s → 2 s → 4 s) on delivery failure
- Dead-letter queue (`webhook_dlq` Kafka topic) filling under sustained failures
- Celery `retry_failed_webhooks` job draining the DLQ (runs every 60 s)
- Notification-worker receiving `task_created` events while the webhook storm runs

**Setup — configure webhook failures before running**

Option A: restart webhook-simulator with a high default fail rate:
```bash
# Edit workers/notification-worker/.env or set inline:
DEFAULT_FAIL_RATE=0.9 \
docker compose -f infra/docker-compose.yml up -d --no-deps webhook-simulator
```

Option B: inject latency via Toxiproxy (no restart needed):
```bash
# Slow the SMTP path as a proxy for the webhook path
curl -s -X POST http://localhost:8474/proxies/mailhog-smtp/toxics \
  -H 'Content-Type: application/json' \
  -d '{"name":"latency","type":"latency","attributes":{"latency":3000,"jitter":500}}'
```

**Three concurrent scenarios**

```
organic_task_events   5 VUs × 3 min  → POST /tasks → task_created Kafka event → webhook attempt
direct_webhook_flood  5 VUs × 3 min  → POST /webhooks/send → immediate webhook attempt
simulator_baseline    2 VUs × 3 min  → POST webhook-sim /receive-webhook directly (fail_rate=0.9)
```

**Run**
```bash
k6 run -e FAIL_RATE=0.9 load-tests/scripts/retry_storm.js
```

**What to observe**

| Where | What to look for |
|---|---|
| Kafka UI `localhost:8080` | `webhook_dlq` topic depth growing during test, draining in 60-s windows (Celery retries) |
| Flower `localhost:5555` | `retry_failed_webhooks` task execution count and last-run time |
| webhook-dispatcher logs | `webhook_attempt_failed`, `webhook_failed_permanently`, DLQ-related structlog events |
| k6 output | `webhook_accepted_202` (integration-service accepted **queued** request) vs `simulator_fail_rate` (~0.9) |
| Jaeger `localhost:16686` | Traces: integration-service (HTTP) vs webhook-dispatcher (no HTTP server in lab — stdout logs) |

**Clean up after** (remove Toxiproxy toxic):
```bash
curl -s -X DELETE http://localhost:8474/proxies/mailhog-smtp/toxics/latency
```

---

### 4. `slow_clients.js` — Long-held connections

**What it tests**
- Connection pool exhaustion under many idle keep-alive connections
- Nginx `proxy_read_timeout 30 s` — heavy readers with >30 s think time trigger upstream timeout
- Postgres idle connection accumulation (`pg_stat_activity`)
- Graceful degradation: normal requests must still succeed while slow clients hold connections

**Three concurrent user types**

```
normal_reader   10 VUs  1-3 s  think  → baseline; must stay healthy throughout
slow_browser    30 VUs  8-20 s think  → holds keep-alive connections; connection pool pressure
heavy_reader    10 VUs  25-35 s think → approaches proxy_read_timeout; may receive 504 via Toxiproxy
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
| Prometheus | `pg_stat_activity_count{state="idle"}` creeping up under slow browser load |
| k6 output | `last_think_time_ms` gauge showing distribution of think times |

**Expected thresholds** — test PASSES if:
- `normal_reader_ok count > 50`
- `http_req_failed rate < 15%`
- `nginx_504_timeouts count < 100`

---

## Configuration Reference

| Environment variable | Default | Description |
|---|---|---|
| `BASE_URL` | `http://localhost` | Nginx entry point for all API calls |
| `WEBHOOK_SIM_URL` | `http://localhost:8004` | Direct access to webhook-simulator |
| `VUS` | `20` | VU count override for `concurrency.js` |
| `FAIL_RATE` | `0.9` | Failure rate passed to `retry_storm.js` simulator baseline |
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

## Project Layout

```
load-tests/
├── README.md                  ← this file
├── lib/
│   └── helpers.js             ← login, requestId, reqTags, auth/anon headers, HTTP wrappers
└── scripts/
    ├── baseline.js            ← steady / long soak (12h via --duration)
    ├── chaos_mode.js          ← retry-once + random sleep; chaos training
    ├── spike_traffic.js       ← sudden spike, Nginx rate limit, cache warm-up
    ├── concurrency.js         ← steady-state mixed workload, full lifecycle
    ├── retry_storm.js         ← webhook failures, DLQ, Celery retries
    └── slow_clients.js        ← connection pool exhaustion, proxy timeouts
```

Repo root `Makefile` exposes `make load-*` targets for the scripts above.
