# Testing architecture: integration infra and integration catalogue (P6)

## 6.7 Integration infra
- saas_testkit/infra/compose.py: when the stack is already up (CI) read BASE_URL (gateway :8001) and NGINX_URL (:80) from env; otherwise the controller runs `docker compose -f infra/docker-compose.yml -f infra/docker-compose.test.yml up -d --build <explicit service list>` and polls /health of every service (--wait only covers services with healthchecks). KEEP_STACK=1 keeps the stack, otherwise `down -v`.
- Seed and login once per run under FileLock (scripts/seed_dev.py or idempotent SQL). Tokens go into a shared token file with an expiry check (refresh when the JWT is close to exp); workers only read it. Playwright storage_state is derived from the same login.
- docker-compose.test.yml: publishes api-gateway on host :8001 (simulator owns :8000); adds wiremock on :8089; sets WEBHOOK_URL of both webhook-dispatcher and scheduler-worker to WireMock (must match: S2 checks DLQ replay); shortens timing knobs (retry/backoff, DLQ replay and cleanup intervals) via env. nginx is not modified. Functional tests use the gateway; real nginx :80 serves UI tests and 2-3 dedicated edge tests (429 on auth burst, forwarded headers).
- postgres in the integration stack gets the ADR-18 tuning in the same override file (command + tmpfs, arch-core-infra.md §6.2); do not touch the base infra/docker-compose.yml.
- WireMock isolation: the dispatcher sends everything to one URL, so each test registers a stub matched on its own payload.id (JSONPath) inside a unique scenario, plus a low-priority catch-all 200 for everyone else; assertions read the request journal filtered by the same id.
- Frontend for CI: vite build + preview (not the dev server).
- Kafka: integration/UI use the stack's own broker, component/contract use Redpanda (ADR-5); both read through KafkaEventReader.

## Integration catalogue (characterise first; record surprises in KNOWN_ISSUES.md)
integration/services: every service /health through gateway; auth->gateway->task with real JWT; nginx 429 on auth burst and forwarded headers (dedicated, serial); /metrics exposes expected series after traffic.
integration/scenarios:
- S1 task lifecycle with side effects: Kafka task_created with envelope -> MailHog email with unique title -> WireMock got webhook with Idempotency-Key; transitions -> task_updated.
- S2 webhook failure -> retries (WireMock scenario 503,503,200) -> success; and permanent failure -> DLQ message -> scheduler replay (slow).
- S3 inbound path simulator -> gateway -> receiver -> webhook_inbound.
- S4 idempotent duplicate delivery.
- S5 resilience (chaos, nightly): Toxiproxy latency/reset on SMTP -> API stays healthy, mail arrives after toxic removed; Redis paused -> API still works.
