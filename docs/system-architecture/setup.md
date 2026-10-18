# Setup

Local run of the lab: `core` profile, then `core` + `observability`. Commands assume the repository root unless the block says `cd infra`.

## Prerequisites


| Tool           | Requirement                                                                                   |
| -------------- | --------------------------------------------------------------------------------------------- |
| Docker         | Required                                                                                      |
| Docker Compose | 2.24 or newer for the test stack                                                              |
| Python         | Seed image `python:3.14-slim` (`load-tests/README.md`). Service images are `python:3.11-slim` |
| k6             | 1.7.1 (`grafana/k6:1.7.1`). Scripts were checked with k6 v1.7.1                               |


k6 on macOS:

```bash
brew install k6
k6 version   # k6 v1.7.1
```

Load-test usage is in `load-tests/README.md`.

## Environment

```bash
cp infra/.env.example infra/.env
cp frontend/.env.example frontend/.env
```

`infra/.env` is the env file for the one-shot `migrations` service. Postgres and postgres-exporter read `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` from the same file. The seed URL in [Seed](#seed) must use those three values. Lab values used by the seed command are `admin` / `admin` / `saas`.


| Variable             | In `infra/.env.example`                          | Who reads it                                                  |
| -------------------- | ------------------------------------------------ | ------------------------------------------------------------- |
| `POSTGRES_USER`      | empty                                            | `postgres`, `migrations`, postgres-exporter                   |
| `POSTGRES_PASSWORD`  | empty                                            | same                                                          |
| `POSTGRES_DB`        | empty                                            | same                                                          |
| `KAFKA_BROKER`       | `kafka:9092`                                     | TBD (compose sets Kafka listeners on the `kafka` service)     |
| `REDIS_HOST`         | `redis`                                          | TBD (services use `REDIS_URL` in their own env files)         |
| `SENTRY_DSN`         | `https://<key>@<org>.ingest.sentry.io/<project>` | `SENTRY_DSN` on core app services; frontend `VITE_SENTRY_DSN` |
| `TELEGRAM_BOT_TOKEN` | empty                                            | Grafana                                                       |
| `TELEGRAM_CHAT_ID`   | empty                                            | Grafana                                                       |
| `GRAFANA_BASE_URL`   | `http://localhost:3000`                          | Grafana                                                       |
| `JAEGER_BASE_URL`    | `http://localhost:16686`                         | Grafana                                                       |
| `KIBANA_BASE_URL`    | `http://localhost:5601`                          | Grafana                                                       |
| `GITHUB_REPO_URL`    | `https://github.com/YOUR_GITHUB_REPO`            | Grafana                                                       |


Grafana receives `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GRAFANA_BASE_URL`, `JAEGER_BASE_URL`, `KIBANA_BASE_URL`, and `GITHUB_REPO_URL` from the shell environment of Compose (the `grafana` service `environment` block). Set the Telegram pair and replace `GITHUB_REPO_URL` before the first observability start. See [Grafana Telegram contact point](#grafana-telegram).

`SENTRY_TRACES_SAMPLE_RATE` is not in `infra/.env.example`. The frontend service defaults it to `1.0`.

The Compose `frontend` service does not load `frontend/.env`. It sets:


| Variable                         | Compose value                       |
| -------------------------------- | ----------------------------------- |
| `VITE_API_URL`                   | `http://localhost`                  |
| `VITE_SENTRY_DSN`                | `${SENTRY_DSN:-}`                   |
| `VITE_SENTRY_TRACES_SAMPLE_RATE` | `${SENTRY_TRACES_SAMPLE_RATE:-1.0}` |


`frontend/.env.example` also documents `VITE_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`. Left unset, the example says the browser uses `http://localhost/otel/v1/traces`.

Compose `env_file` entries (copy each service `.env.example` to the `.env` path). Required keys are from `testing/docs/human/SUT_MAP_FULL.md`. Example-file bodies were not in the source set for this page.


| `env_file`                                          | Required settings                                                                                                                                            |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `services/core/api-gateway/.env`                    | `JWT_SECRET`, `AUTH_SERVICE_URL`, `TASK_SERVICE_URL`, `INTEGRATION_SERVICE_URL`                                                                              |
| `services/core/auth-service/.env`                   | `JWT_SECRET`, `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `REDIS_URL`                                                              |
| `services/core/task-service/.env`                   | `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `REDIS_URL`, `KAFKA_BOOTSTRAP_SERVERS`                                                 |
| `services/core/webhook-receiver/.env`               | `KAFKA_BOOTSTRAP_SERVERS`                                                                                                                                    |
| `services/external/external-service-simulator/.env` | `INTEGRATION_SERVICE_WEBHOOK_URL`                                                                                                                            |
| `services/core/webhook-dispatcher/.env`             | `KAFKA_BOOTSTRAP_SERVERS`, `WEBHOOK_URL`                                                                                                                     |
| `workers/notification-worker/.env`                  | `KAFKA_BOOTSTRAP_SERVERS`, `SMTP_HOST` (compose overrides SMTP with `SMTP_HOST` default `toxiproxy`, `SMTP_PORT` default `11025`)                            |
| `workers/scheduler-worker/.env`                     | `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `KAFKA_BOOTSTRAP_SERVERS`, `WEBHOOK_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` |


Lab `JWT_SECRET` value recorded in the SUT map: `dev-secret-change-in-production`. `OTLP_ENDPOINT` defaults to `http://otel-collector:4317` when unset. `POSTGRES_PORT` defaults to `5432`.

## Start

```bash
cd infra
docker compose --profile core up -d
docker compose --profile core --profile observability up -d
docker compose ps
```

`core` starts Nginx, api-gateway, auth-service, task-service, webhook-receiver, webhook-dispatcher, external-service-simulator, notification-worker, scheduler-worker, Kafka, kafka-exporter, Redis, Postgres, postgres-exporter, frontend, MailHog, Toxiproxy, and the one-shot `migrations` container (`alembic upgrade head`).

`observability` starts Jaeger, otel-collector, Prometheus, Grafana, Fluent Bit, Elasticsearch, and Kibana. Profiles in this repo are `core` and `observability`.

Wait until `migrations` has exited successfully and the healthchecks are healthy before seeding.

## Seed

Postgres publishes no host port. `localhost:5432` from the host does not reach it. From the repository root, after Postgres is up:

```bash
docker run --rm --network container:postgres \
  -e DATABASE_URL=postgresql://admin:admin@127.0.0.1:5432/saas \
  -v "$PWD/scripts:/scripts" \
  python:3.14-slim \
  bash -c "pip install -q -r /scripts/requirements.txt && python /scripts/seed_dev.py"
```

`DATABASE_URL` must match `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB`. The command above is the lab triple `admin` / `admin` / `saas`.

Migrations do not insert users. The seed is manual. It inserts `admin` / `admin123` (role `admin`) and `user` / `user123` (role `user`), `ON CONFLICT (username) DO NOTHING`, plus ten tasks.

## Frontend and logins

UI: `http://localhost:5173` (`frontend`, host `5173`).

API from the host: Nginx `http://localhost` (host `80`). api-gateway `8000` is not published.


| Username | Password   | Role    |
| -------- | ---------- | ------- |
| `admin`  | `admin123` | `admin` |
| `user`   | `user123`  | `user`  |


![Frontend](../images/project-dashboard-frontend.png)

Token check:

```bash
curl -s -X POST http://localhost/auth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=admin&password=admin123'
```

Send `Authorization: Bearer <access_token>` on `/tasks/*`.

## Verification

UIs with a published host port in `infra/docker-compose.yml`.


| UI         | URL                      | Profile         |
| ---------- | ------------------------ | --------------- |
| Frontend   | `http://localhost:5173`  | `core`          |
| MailHog    | `http://localhost:8025`  | `core`          |
| Jaeger     | `http://localhost:16686` | `observability` |
| Prometheus | `http://localhost:9090`  | `observability` |
| Grafana    | `http://localhost:3000`  | `observability` |
| Kibana     | `http://localhost:5601`  | `observability` |


Grafana admin user and password: TBD (not set in the compose service). Elasticsearch is started with `xpack.security.enabled: "false"`. Kibana has no credentials in compose.

## Manual steps



### Kibana data view



Fluent Bit writes Elasticsearch indices with `Logstash_Prefix` `saas-debug-lab` and `Logstash_DateFormat` `%Y.%m.%d` (daily indices `saas-debug-lab-YYYY.MM.DD`). The Grafana Elasticsearch datasource uses index `saas-debug-lab-*` and time field `@timestamp`.

1. Open Kibana (`http://localhost:5601`).
2. Stack Management → Data Views.
3. Create a data view named `saas-debug-lab` on `saas-debug-lab-*`.
4. Set the timestamp field to `@timestamp`.

![Kibana create data view](../images/kibana-setup-create-data-view.png)

### Grafana Telegram contact point



`observability/grafana/provisioning/alerting/contact-points.yml` defines contact point `telegram` (receiver uid `telegram-receiver`). `bottoken` is `${TELEGRAM_BOT_TOKEN}` and `chatid` is `${TELEGRAM_CHAT_ID}`. Grafana gets both from the compose `environment` block, which reads `infra/.env`.

Set both variables before starting Grafana. To change them later, edit `infra/.env` and recreate Grafana, or change the contact point in the Grafana UI. The provisioning directory is mounted read-only.

### Grafana Elasticsearch data links



The Elasticsearch datasource in `observability/grafana/provisioning/datasources/prometheus.yaml` has four data links on field `trace_id` (labels: Explore trace (Grafana), Jaeger, Kibana, Sentry). Each URL contains `${__value.raw}`.

After Grafana is up: Connections → Data sources → Elasticsearch. Paste `${__value.raw}` into every data link so the macro stays literal. URL shapes are in [How they link](observability.md#how-they-link).

![Grafana datasource data-link workaround](../images/grafana-datasources-manual-workaround.png)

## Stop and clean

```bash
cd infra
docker compose --profile core --profile observability down -v
```

`-v` removes named volumes `postgres_data`, `redis_data`, `grafana_data`, `elasticsearch_data`, and `prometheus_data`.