# SaaS Debug Lab

## Overview

SaaS Debug Lab is a production-like microservices system designed to simulate real-world distributed system failures and practice incident investigation.

The platform models a simplified SaaS / FinTech backend with asynchronous processing, external integrations, and observability tooling.

The system is intentionally designed to:

- behave like a real production environment
- fail in realistic ways
- provide full visibility via logs, metrics, and tracing
- inject failures intentionally (chaos engineering)

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

Edit **`infra/.env`** and set at least:

| Variable | Purpose |
|----------|---------|
| `POSTGRES_USER` | Database user (lab examples often use `admin`) |
| `POSTGRES_PASSWORD` | Database password (lab examples often use `admin`) |
| `POSTGRES_DB` | Database name (lab examples often use `saas`) |

Keep these values consistent with the **`DATABASE_URL`** you use for seeding (step 5). Optional: `DD_*` and `SENTRY_DSN` if you use Datadog or Sentry profiles.

### 3. Start the stack

From the **repository root**:

```bash
cd infra
docker compose --profile core up -d
```

This starts Nginx, api-gateway, auth-service, task-service, integration-service, webhook-dispatcher, webhook-simulator, workers (notification-worker, **scheduler-worker**), Flower, Kafka, Redis, Postgres, frontend, Kafka UI, MailHog, Toxiproxy, and one-off **Alembic migrate** jobs (`auth-migrate`, `task-migrate`) before the app services become healthy.

**Optional — full observability** (Jaeger, Prometheus, Grafana, Elasticsearch, Kibana, Fluent Bit, Redis Insight):

```bash
docker compose --profile core --profile observability up -d
```

**Optional — Datadog Agent** (requires `DD_API_KEY` in `infra/.env`):

```bash
docker compose --profile core --profile datadog up -d
```

Wait until containers are healthy (`docker compose ps`).

### 4. API entry point

All HTTP API traffic from the host goes through **Nginx on port 80**:

- **Base URL:** `http://localhost`
- **Health (via gateway):** `GET http://localhost/health` (and service-specific `/health` routes behind the gateway as documented in `docs/SERVICE_MAP.md`)

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

The SPA is served at **`http://localhost:5173`** when the `frontend` container is up.

```bash
cp frontend/.env.example frontend/.env
# Ensure VITE_API_URL targets Nginx, e.g. http://localhost
```

Rebuild or restart frontend if you change `frontend/.env`:

```bash
cd infra && docker compose --profile core up -d --build frontend
```

### 7. Quick verification

| Check | URL / command |
|-------|----------------|
| Kanban / UI | `http://localhost:5173` — log in with `admin` / `admin123` |
| Kafka UI | `http://localhost:8080` |
| Flower (Celery) | `http://localhost:5555` |
| MailHog | `http://localhost:8025` |
| Jaeger (if observability profile) | `http://localhost:16686` |
| Prometheus | `http://localhost:9090` |
| Grafana | `http://localhost:3000` |
| Kibana | `http://localhost:5601` |

### 8. Load tests (k6)

Install [k6](https://k6.io/docs/get-started/installation/). From **repo root**:

```bash
make load-baseline
# or: k6 run load-tests/scripts/concurrency.js
```

See **`load-tests/README.md`** for scenarios, env vars (`BASE_URL`, `FAIL_RATE`, …), and long runs (e.g. `k6 run --duration 12h load-tests/scripts/baseline.js`).

### 9. Chaos scripts

From **repo root**:

```bash
make chaos-random
make chaos-scenario SCENARIO=webhook_failure
```

See **`chaos/README.md`**. After `kafka_lag`, run `docker unpause webhook-dispatcher` if the dispatcher was paused.

### 10. Stop the stack

```bash
cd infra
docker compose --profile core --profile observability --profile datadog down
```

(Use only the profiles you actually started.)

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
- **auth-service** — authentication, JWT issuance, user store in Postgres
- **task-service** — task CRUD, state machine, Redis cache-aside, Kafka producer (`task_created`, `task_updated`)
- **integration-service** — `/webhooks/inbound`, `/webhooks/send`; Kafka producer only
- **webhook-dispatcher** — consumes Kafka, delivers outbound webhooks, retries, DLQ
- **webhook-simulator** — external webhook test double (`fail_rate`, `delay`, `status`)
- **notification-worker** — consumes `task_created`, sends SMTP (via Toxiproxy → MailHog)
- **scheduler-worker** — Celery + Beat: DLQ replay, old-task cleanup; **Flower** on port 5555
- **Postgres**, **Redis**, **Kafka** — data, cache, events

For ports, envelopes, and request diagrams, see **`docs/SERVICE_MAP.md`** and **`docs/ARCHITECTURE.md`**.

---

## Observability stack

- **Logging** — structured JSON (structlog); optional **Fluent Bit → Elasticsearch → Kibana**
- **Metrics** — **Prometheus** scrapes api-gateway, auth-service, task-service; **Grafana** optional
- **Tracing** — **Jaeger** + OpenTelemetry in services (optional profile)

---

## Failure simulation

- **Concepts:** `docs/FAILURE_PRIMITIVES.md`, `docs/SCENARIO_MAPPING.md`
- **Automation:** **`chaos/`** primitives and scenarios (`chaos/README.md`, `Makefile` targets `chaos-*`, `break-*`, `slow-db`)
- **Load + chaos:** run `make load-spike` or other `load-*` targets while executing scenarios

---

## Debugging scenarios

The repo includes guided exercises and playbooks under **`docs/`** (e.g. debugging scenarios, incident entry points, troubleshooting). See **`docs/FILE_STRUCTURE.md`** for the full doc index.

---

## Learning artifacts

- Incident-style playbooks and step-by-step labs in `docs/`
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
