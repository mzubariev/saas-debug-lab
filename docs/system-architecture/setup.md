# Setup

Local run of the lab: `core` profile, then `core` + `observability`. Commands assume the repository root unless the block says `cd infra`.

## Prerequisites


| Tool               | Requirement                                                                      |
| ------------------ | -------------------------------------------------------------------------------- |
| Docker             | Required                                                                         |
| Docker Compose     | v5.5.1 or newer for the test stack                                               |
| k6                 | 1.7.1 (`grafana/k6:1.7.1`). Only for load tests and synthetic checks             |
| Python 3.14 and uv | Only to run the test framework, see [testing/README.md](../../testing/README.md) |


The seed runs in a container, so the lab itself needs no Python on the host.

k6 on macOS:

```bash
brew install k6
k6 version   # k6 v1.7.1
```

Load-test usage is in [load-tests/README.md](../../load-tests/README.md).

## Environment

Infra and frontend env files:

```bash
cp infra/.env.example infra/.env
cp frontend/.env.example frontend/.env
```

Service env files (Compose `env_file` entries; the `.env` files are gitignored):

```bash
cp services/core/api-gateway/.env.example services/core/api-gateway/.env
cp services/core/auth-service/.env.example services/core/auth-service/.env
cp services/core/task-service/.env.example services/core/task-service/.env
cp services/core/webhook-receiver/.env.example services/core/webhook-receiver/.env
cp services/external/external-service-simulator/.env.example services/external/external-service-simulator/.env
cp services/core/webhook-dispatcher/.env.example services/core/webhook-dispatcher/.env
cp workers/notification-worker/.env.example workers/notification-worker/.env
cp workers/scheduler-worker/.env.example workers/scheduler-worker/.env
```

`infra/.env` is the env file for the one-shot `migrations` service. Postgres and postgres-exporter read `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` from the same file, and they are empty in the example. Set them before the first start. The seed URL in [Seed](#seed) must use the same three values. The lab values are `admin` / `admin` / `saas`.


| Variable                  | In `infra/.env.example`                                   | Who reads it                                                           |
| ------------------------- | --------------------------------------------------------- | ---------------------------------------------------------------------- |
| `POSTGRES_USER`           | empty                                                     | `postgres`, `migrations`, postgres-exporter                            |
| `POSTGRES_PASSWORD`       | empty                                                     | same                                                                   |
| `POSTGRES_DB`             | empty                                                     | same                                                                   |
| `SENTRY_DSN`              | `https://<key>@<org>.ingest.sentry.io/<project>`          | Core app services; the frontend gets it as `VITE_SENTRY_DSN`. Optional |
| `TELEGRAM_BOT_TOKEN`      | empty                                                     | Grafana                                                                |
| `TELEGRAM_CHAT_ID`        | empty                                                     | Grafana                                                                |
| `GRAFANA_BASE_URL`        | `http://localhost:3000`                                   | Grafana                                                                |
| `GRAFANA_BASE_URL_IP`     | `http://127.0.0.1:3000`                                   | Grafana                                                                |
| `JAEGER_BASE_URL`         | `http://localhost:16686`                                  | Grafana                                                                |
| `KIBANA_BASE_URL`         | `http://localhost:5601`                                   | Grafana                                                                |
| `SENTRY_BASE_URL_PROJECT` | `https://<key>@<org>.sentry.io/issues/?project=<project>` | Grafana                                                                |
| `GITHUB_REPO_URL`         | `https://github.com/YOUR_GITHUB_REPO`                     | Grafana                                                                |


Compose substitutes these into the `grafana` service `environment` block from `infra/.env` (run Compose from `infra/`) or from the shell. 

`SENTRY_TRACES_SAMPLE_RATE` is not in `infra/.env.example`. The frontend service defaults it to `1.0`.

The Compose `frontend` service does not load `frontend/.env`. It sets:


| Variable                         | Compose value                       |
| -------------------------------- | ----------------------------------- |
| `VITE_API_URL`                   | `http://localhost`                  |
| `VITE_SENTRY_DSN`                | `${SENTRY_DSN:-}`                   |
| `VITE_SENTRY_TRACES_SAMPLE_RATE` | `${SENTRY_TRACES_SAMPLE_RATE:-1.0}` |


`frontend/.env.example` also documents `VITE_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`. Left unset, the browser uses `http://localhost/otel/v1/traces`.

Settings each service requires (a missing one fails startup; the example files already hold lab values):


| `env_file`                                          | Required settings                                                                                                                                            |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `services/core/api-gateway/.env`                    | `JWT_SECRET`, `AUTH_SERVICE_URL`, `TASK_SERVICE_URL`, `INTEGRATION_SERVICE_URL`                                                                              |
| `services/core/auth-service/.env`                   | `JWT_SECRET`, `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `REDIS_URL`                                                              |
| `services/core/task-service/.env`                   | `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `REDIS_URL`, `KAFKA_BOOTSTRAP_SERVERS`                                                 |
| `services/core/webhook-receiver/.env`               | `KAFKA_BOOTSTRAP_SERVERS`                                                                                                                                    |
| `services/external/external-service-simulator/.env` | `INTEGRATION_SERVICE_WEBHOOK_URL`                                                                                                                            |
| `services/core/webhook-dispatcher/.env`             | `KAFKA_BOOTSTRAP_SERVERS`, `WEBHOOK_URL`                                                                                                                     |
| `workers/notification-worker/.env`                  | `KAFKA_BOOTSTRAP_SERVERS`, `SMTP_HOST` (Compose overrides it with default `toxiproxy`, `SMTP_PORT` default `11025`)                                          |
| `workers/scheduler-worker/.env`                     | `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `KAFKA_BOOTSTRAP_SERVERS`, `WEBHOOK_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` |


The lab `JWT_SECRET` is `dev-secret-change-in-production`. It is a lab value, never use it elsewhere. `OTLP_ENDPOINT` defaults to `http://otel-collector:4317` when unset. `POSTGRES_PORT` defaults to `5432`.

## Start

```bash
cd infra
docker compose --profile core up -d
docker compose --profile core --profile observability up -d
docker compose ps
```

`core` starts Nginx, api-gateway, auth-service, task-service, webhook-receiver, webhook-dispatcher, external-service-simulator, notification-worker, scheduler-worker, Kafka, kafka-exporter, Redis, Postgres, postgres-exporter, frontend, MailHog, Toxiproxy, and the one-shot `migrations` container (`alembic upgrade head`).

`observability` starts Jaeger, otel-collector, Prometheus, Grafana, Fluent Bit, Elasticsearch, and Kibana. The profiles in this repo are `core` and `observability`.

Wait until `migrations` has exited successfully and the healthchecks are healthy before seeding.

## Seed

Postgres publishes no host port, so `localhost:5432` from the host does not reach it. From the repository root, after Postgres is up:

```bash
docker run --rm --network container:postgres \
  -e DATABASE_URL=postgresql://admin:admin@127.0.0.1:5432/saas \
  -v "$PWD/scripts:/scripts" \
  python:3.14-slim \
  bash -c "pip install -q -r /scripts/requirements.txt && python /scripts/seed_dev.py"
```

`DATABASE_URL` must match `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB`. The command above uses the lab triple `admin` / `admin` / `saas`.

Migrations do not insert users, so the seed is a manual step. It inserts `admin` / `admin123` (role `admin`) and `user` / `user123` (role `user`) with `ON CONFLICT (username) DO NOTHING`, plus ten tasks.

## Frontend and logins

UI: `http://localhost:5173` (`frontend`, host `5173`).

API from the host: Nginx `http://localhost` (host `80`). api-gateway `8000` is not published.


| Username | Password   | Role    |
| -------- | ---------- | ------- |
| `admin`  | `admin123` | `admin` |
| `user`   | `user123`  | `user`  |


<p align="center">
  <img src="../images/project-dashboard-frontend.png" alt="Frontend" width="700">
</p>

Token check:

```bash
curl -s -X POST http://localhost/auth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=admin&password=admin123'
```

Send `Authorization: Bearer <access_token>` on `/tasks/*`.

## Verification

Published host ports in `infra/docker-compose.yml`.


| What                       | URL                      | Profile         |
| -------------------------- | ------------------------ | --------------- |
| Frontend                   | `http://localhost:5173`  | `core`          |
| API (Nginx)                | `http://localhost`       | `core`          |
| external-service-simulator | `http://localhost:8000`  | `core`          |
| MailHog                    | `http://localhost:8025`  | `core`          |
| Toxiproxy management API   | `http://localhost:8474`  | `core`          |
| Jaeger                     | `http://localhost:16686` | `observability` |
| Prometheus                 | `http://localhost:9090`  | `observability` |
| Grafana                    | `http://localhost:3000`  | `observability` |
| Kibana                     | `http://localhost:5601`  | `observability` |


Grafana has no admin override in Compose, so the image default applies: `admin` / `admin`, and Grafana asks for a new password on the first login. Elasticsearch runs with `xpack.security.enabled: "false"` and Kibana has no credentials.

## Manual steps

These steps are not automated. Do them once after the first start.

### Kibana data view

Fluent Bit writes daily indices `saas-debug-lab-YYYY.MM.DD` (`Logstash_Prefix` `saas-debug-lab`, `Logstash_DateFormat` `%Y.%m.%d`). The Grafana Elasticsearch datasource uses index `saas-debug-lab-*` and time field `@timestamp`.

1. Open Kibana (`http://localhost:5601`).
2. Stack Management → Data Views.
3. Create a data view named `saas-debug-lab` on `saas-debug-lab-*`.
4. Set the timestamp field to `@timestamp`.

<p align="center">
  <img src="../images/kibana-setup-create-data-view.png" alt="Kibana create data view" width="700">
</p>

## Stop and clean

```bash
cd infra
docker compose --profile core --profile observability down -v
```

`-v` removes the named volumes `postgres_data`, `redis_data`, `grafana_data`, `elasticsearch_data`, and `prometheus_data`.