# SaaS Debug Lab

## Overview

**SaaS Debug Lab** is a production-like microservices system designed to simulate real-world distributed system failures and enable hands-on incident investigation.

The platform models a simplified SaaS backend, incorporating synchronous and asynchronous workflows, external service integrations, and a full observability stack (logs, metrics, and tracing).

The system is intentionally engineered to:

- behave like a real production environment
- introduce controlled failures (chaos engineering)
- fail in realistic ways
- provide deep visibility into system behavior

From a product perspective, the application itself is intentionally simple: a task management board where users can log in, create tasks, and manage their workflow by moving tasks between states such as **“In Progress”** and **“Completed”** via drag-and-drop.

---

## Getting started (clone → run locally)

Follow these steps on macOS or Linux with **Docker** and **Docker Compose** installed.

### 1. Clone the repository

```bash
git clone <repository-url> saas-debug-lab
cd saas-debug-lab
```

### 2. Configure environment

```bash
cp infra/.env.example infra/.env
```

Edit `**infra/.env**` and set at least:


| Variable            | Purpose                                      |
| ------------------- | -------------------------------------------- |
| `POSTGRES_USER`     | Database user (lab examples use `admin`)     |
| `POSTGRES_PASSWORD` | Database password (lab examples use `admin`) |
| `POSTGRES_DB`       | Database name (lab examples use `saas`)      |


Keep these values consistent with the `**DATABASE_URL**` you use for seeding (step 5). Optional: `SENTRY_DSN`. For **Datadog APM**, set `DD_API_KEY` (and optionally `DD_SITE`, `DD_ENV`, `DD_VERSION`) when using `[infra/docker-compose.datadog.yml](infra/docker-compose.datadog.yml)` — see **Tracing modes** below.

### 3. Start the stack

From the **repository root**:

```bash
cd infra
docker compose --profile core up -d
```

This starts Nginx, api-gateway, auth-service, task-service, webhook-receiver, webhook-dispatcher, external-service-simulator, workers (notification-worker, **scheduler-worker**), Flower, Kafka (+ **kafka-exporter**), Redis, Postgres (+ **postgres-exporter**), frontend, Kafka UI, MailHog, Toxiproxy, and a one-shot `**migrations`** container (`alembic upgrade head` for `users` + `tasks`) before auth-service and task-service start.

**Database:** set `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` in `**infra/.env`** — the same file is used by the Postgres service and the `migrations` job.

**Optional — full observability** (Jaeger, OpenTelemetry Collector, Prometheus, Grafana, Elasticsearch, Kibana, Fluent Bit, Redis Insight):

```bash
docker compose --profile core --profile observability up -d
```

**Tracing modes** (pick **one** — do not combine `observability` with the Datadog override):


| Mode                                                      | Command (from `infra/`)                                                                                     |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| **OpenTelemetry → Collector → Jaeger**                    | `docker compose --profile core --profile observability up -d`                                               |
| **Datadog APM** (`ddtrace-run` only; no Jaeger/Collector) | `docker compose -f docker-compose.yml -f docker-compose.datadog.yml --profile core --profile datadog up -d` |


For Datadog, set `DD_API_KEY` in `**infra/.env`**. Switching modes is done **only** via compose files, never by mixing env vars.

Wait until containers are healthy (`docker compose ps`).

### 4. API entry point

All HTTP API traffic from the host goes through **Nginx on port 80**:

- **Base URL:** `http://localhost`
- **Health (via gateway):** `GET http://localhost/health` (and service-specific `/health` routes behind the gateway as documented in `[docs/system-architechture/SERVICE_MAP.md](docs/system-architechture/SERVICE_MAP.md)`)

Default **JWT login** (after seeding, step 5):

- **Username:** `admin`
- **Password:** `admin123`

Example:

```bash
curl -s -X POST http://localhost/auth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=admin&password=admin123'
```

Use the returned `access_token` as `Authorization: Bearer <token>` for `/tasks/*`.

### 5. Seed the database (recommended)

Migrations run via Compose; **seed data** is not applied automatically. On the host (Python 3.11+):

```bash
cd ..   # back to repo root if you are still in infra/
pip install -r scripts/requirements.txt
export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:5432/${POSTGRES_DB}"
# Example matching common lab defaults:
# DATABASE_URL=postgresql://admin:admin@localhost:5432/saas
python scripts/seed_dev.py
```

This creates users (`admin` / `user`) and sample tasks. See `scripts/seed_dev.py` for details.

### 6. Frontend (optional)

The SPA is served at `**http://localhost:5173**` when the `frontend` container is up.

```bash
cp frontend/.env.example frontend/.env
# Ensure VITE_API_URL targets Nginx, e.g. http://localhost
# Optional: VITE_SENTRY_DSN — in Compose, the frontend service maps host SENTRY_DSN into VITE_SENTRY_DSN automatically
```

Rebuild or restart frontend if you change `frontend/.env`:

```bash
cd infra && docker compose --profile core up -d --build frontend
```

### 7. Quick verification


| Check             | URL / command                                              |
| ----------------- | ---------------------------------------------------------- |
| Kanban / UI       | `http://localhost:5173` — log in with `admin` / `admin123` |
| Kafka UI          | `http://localhost:8080`                                    |
| Redis Insight     | `http://localhost:5540`                                    |
| Flower (Celery)   | `http://localhost:5555`                                    |
| MailHog           | `http://localhost:8025`                                    |
| Jaeger            | `http://localhost:16686`                                   |
| Prometheus        | `http://localhost:9090`                                    |
| Grafana           | `http://localhost:3000`                                    |
| Pyroscope         | `http://localhost:4040`                                    |
| Kibana            | `http://localhost:5601`                                    |


### 8. Load tests (k6)

Install [k6](https://k6.io/docs/get-started/installation/). From **repo root**:

```bash
make load-baseline
# or: k6 run load-tests/scripts/concurrency.js
```

See `**load-tests/README.md**` for scenarios, env vars (`BASE_URL`, `FAIL_RATE`, …), and long runs (e.g. `k6 run --duration 12h load-tests/scripts/baseline.js`).

### 9. Chaos scripts

From **repo root**:

```bash
make chaos-random
make chaos-scenario SCENARIO=webhook_failure
```

See `**chaos/README.md**`. After `kafka_lag`, run `docker unpause webhook-dispatcher` if the dispatcher was paused.

### 10. Stop the stack

```bash
cd infra
docker compose --profile core --profile observability down
```

If you used the Datadog override, use the same `-f` files and `--profile` flags with `down`. Use only the profiles you actually started.

---

## Objectives

The primary objective is to build practical debugging skills in distributed systems.

### Core capabilities

- Investigate incidents across multiple services
- Analyze logs, metrics, and traces
- Debug Kafka-based event flows
- Identify bottlenecks and failure points
- Understand cascading failures
- Practice real-world escalation workflows

---

## System architecture (summary)

The system follows a microservices architecture with synchronous and asynchronous communication.

### Core components

- **Nginx** — external entry (port 80); rate limits and reverse proxy to api-gateway
- **api-gateway** — routing, JWT validation for `/tasks/*`
- **auth-service** — authentication, JWT issuance, user store in Postgres, Redis cache-aside
- **task-service** — task CRUD, state machine, Redis cache-aside, Kafka producer (`task_created`, `task_updated`)
- **webhook-receiver** — `/webhooks/inbound`; inbound-only Kafka producer (`webhook_inbound` topic)
- **webhook-dispatcher** — consumes Kafka (`task_created`, `task_updated`), delivers outbound webhooks with exponential backoff + jitter, no retry on 4xx, DLQ on permanent failure
- **external-service-simulator** — external webhook test double (`fail_rate`, `delay`, `status`, idempotency deduplication)
- **notification-worker** — consumes `task_created`, sends SMTP (via Toxiproxy → MailHog)
- **scheduler-worker** — Celery + Beat: DLQ replay, old-task cleanup; **Flower** on port 5555
- **Postgres**, **Redis**, **Kafka** — data, cache, events

For ports, envelopes, and request diagrams, see `[docs/system-architechture/SERVICE_MAP.md](docs/system-architechture/SERVICE_MAP.md)` and `[docs/system-architechture/ARCHITECTURE.md](docs/system-architechture/ARCHITECTURE.md)`. Repository layout: `[docs/system-architechture/FILE_STRUCTURE.md](docs/system-architechture/FILE_STRUCTURE.md)`.

---

## Observability stack

- **Logging** — structured JSON (structlog); **Fluent Bit → Elasticsearch → Kibana**
- **Metrics** — **Prometheus** scrapes FastAPI services (`/metrics`), **external-service-simulator**, worker endpoints on **9100** (webhook-dispatcher, notification-worker, scheduler-worker), **kafka-exporter** (:9308), and **postgres-exporter** (:9187). **Grafana** loads provisioned dashboards and alert rules from `observability/grafana/provisioning/`.
- **Tracing** — **OpenTelemetry** → **Collector** → **Jaeger** (with the `observability` profile) in services and the frontend (`frontend/src/telemetry.ts`). **Datadog APM** is a separate compose path only (`[infra/docker-compose.datadog.yml](infra/docker-compose.datadog.yml)`).
- **Errors (optional)** — **Sentry** across FastAPI apps, workers, and the React SPA when `SENTRY_DSN` / `VITE_SENTRY_DSN` are set; shared initialisation lives in `shared/saas_shared/sentry_setup.py`

### Tracing modes (one primary tracer per process)

- **OpenTelemetry + Jaeger** — Base compose + `**observability`** profile. Apps export OTLP to `otel-collector:4317`; OTEL auto-instrumentation (FastAPI, httpx, Redis, SQLAlchemy), W3C Kafka headers, semantic Kafka spans (`saas_shared.kafka_messaging`). `DD_TRACE_ENABLED` is not set.
- **Datadog APM** — Base compose + `**docker-compose.datadog.yml`** + `**datadog`** profile. `ddtrace-run` on service commands; OTEL SDK registration in app code is **skipped** (`DD_TRACE_ENABLED=true` is set only by that override file). Do **not** start Jaeger or the OTel Collector in this mode.

**End-to-end check (OpenTelemetry):** Log in on the UI → create a task → follow one `**trace_id`** in JSON logs (Kibana) and the same trace in Jaeger: expect spans for nginx ingress (via gateway), HTTP client hops, Postgres (SQLAlchemy), Kafka produce/consume (named + semantic attributes), worker processing, and outbound webhook HTTP.

---

## Failure simulation

- **Concepts:** [Failure primitives](docs/incidents-playbooks/PROD_INCIDENTS.md), [Incident patterns](docs/incidents-playbooks/1_INCIDENT_PATTERNS.md), [Debugging scenarios](docs/incidents-playbooks/DEBUGGING_SCENARIOS.md)
- **Automation:** `**chaos/`** primitives and scenarios (`chaos/README.md`, `Makefile` targets `chaos-`*, `break-`*, `slow-db`)
- **Load + chaos:** run `make load-spike` or other `load-`* targets while executing scenarios

---

## Investigation documentation

Guided exercises and playbooks live under `[docs/incidents-playbooks/](docs/incidents-playbooks/)` (see also `[docs/system-architechture/FILE_STRUCTURE.md](docs/system-architechture/FILE_STRUCTURE.md)`). Highlights: [Debugging scenarios](docs/incidents-playbooks/DEBUGGING_SCENARIOS.md), [Incident patterns](docs/incidents-playbooks/1_INCIDENT_PATTERNS.md), [Incident playbooks](docs/incidents-playbooks/2_INCIDENT_PLAYBOOKS.md), [Failure primitives](docs/incidents-playbooks/PROD_INCIDENTS.md).

---

## Learning artifacts

- Incident-style playbooks and step-by-step labs under `[docs/incidents-playbooks/](docs/incidents-playbooks/)` and stack reference under `[docs/system-architechture/](docs/system-architechture/)`
- **Load tests:** `load-tests/README.md`
- **Chaos:** `chaos/README.md`

---

## Target roles

This lab is designed to simulate real responsibilities of:

- Product Support Engineer
- Technical Support Engineer
- Escalation Engineer
- Integration Engineer
- Platform Support Engineer

---

## Non-goals

To keep the project focused:

- no full production hardening
- no complex business domain logic
- no UI-heavy features
- no premature optimization

The focus is debuggability, not product completeness.

---

## Key design principles

- Observability-first — everything must be traceable
- Failure-first design — system is built to break
- Reproducibility — incidents must be repeatable
- Realism over complexity — simulate real issues, not edge-case noise
- Modularity — failures and services are loosely coupled
- Shared Python package (`saas_shared`) — Kafka envelopes, logging, Redis cache helpers, health router, telemetry, and Sentry setup stay DRY across services and workers

