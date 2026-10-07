# Testing architecture: integration infra and integration catalogue (P6)

## 6.7 Integration infra

- saas_testkit/infra/compose.py: when the stack is already up (CI) read BASE_URL (gateway :8001) and NGINX_URL (:80) from env; otherwise the controller runs `docker compose -f infra/docker-compose.yml -f infra/docker-compose.test.yml up -d --build <services from infra/test-stack.services>` and then checks readiness per service kind: FastAPI services via /health, Kafka workers via GET :/metrics, migrations via container exit code 0, third-party containers via their own port. --wait only covers services with healthchecks (mailhog, postgres-exporter, kafka-exporter, frontend now have them; workers and toxiproxy do not). On timeout the helper fails hard and prints `docker compose logs --tail=100` of the services that are not ready (locally and in CI). KEEP_STACK=1 keeps the stack, otherwise `down -v`. `make stack-up` / `make stack-down` wrap this (added in P6.1).
- Seed and login once per run under FileLock (scripts/seed_dev.py reads DATABASE_URL, whose default localhost:5432 does not match the compose file, so set it to the published test port; or use idempotent SQL; users are inserted ON CONFLICT DO NOTHING). Tokens go into a shared token file with an expiry check (refresh when the JWT is close to exp); workers only read it. Playwright storage_state is derived from the same login.
- docker-compose.test.yml: publishes api-gateway on host :8001 (simulator owns :8000); adds wiremock on :8089; sets WEBHOOK_URL of both webhook-dispatcher and scheduler-worker to WireMock (must match: the DLQ replay scenario needs it); selects the frontend `preview` stage; publishes what the base compose keeps internal: Postgres, Redis, the Kafka external listener localhost:9093 and the workers' metrics ports on distinct host ports (for example 9101 dispatcher, 9102 notification, 9103 scheduler; the scheduler binds its metrics port in one prefork child only, so poll that port with retries). Seeding, KafkaEventReader and readiness checks run from the host and need these ports. nginx is not modified. Functional tests use the gateway; real nginx :80 serves UI tests and the 2 dedicated edge tests.
- Timing knobs (env, current values are the defaults): shorten `WEBHOOK_BACKOFF_BASE`, `DLQ_REPLAY_INTERVAL_SECONDS` and `CLEANUP_INTERVAL_SECONDS`. **Keep** `CLEANUP_COMPLETED_TASKS_MINUTES` **at the default 5**: a shorter age would delete completed tasks that other tests still read. The cleanup scenario backdates instead (see S6).
- postgres in the integration stack gets the ADR-18 tuning in the same override file (command + tmpfs, arch-core-infra.md 6.2); do not touch the base infra/docker-compose.yml.
- WireMock isolation: the dispatcher sends everything to one URL, so each test registers a stub matched on its own payload.id (JSONPath) inside a unique scenario, plus a low-priority catch-all 200 for everyone else; assertions read the request journal filtered by the same id.
- Frontend for CI: vite build + preview (not the dev server).
- Tests that must not run in parallel with others (the nginx edge tests) carry @pytest.mark.xdist_group("serial"), and the integration run uses --dist loadgroup.
- Kafka: integration/UI use the stack's own broker, component/contract use Redpanda (ADR-5); both read through KafkaEventReader.



## Integration catalogue

Principle: integration holds only what no lower layer can observe: cross-service wiring and side effects, and the nginx edge. Per-service behaviour lives in component tests, /health and /metrics reachability in smoke. Target: about 8 tests. Characterise first; record surprises in KNOWN_ISSUES.md.

Tiers: T1 = must, T2 = if time (slow/chaos, nightly), T3 = not planned.

### T1

- **auth chain** (integration/services): login -> create task -> read task through the gateway with a real JWT (the first green test of P6.1).
- **nginx edge**, `@pytest.mark.xdist_group("serial")`, real nginx :80:
  - auth burst: about 10 logins within a minute, expect no 429 (empty zone key is not accounted; the documentation says 5 r/min). If confirmed, record BUG-1.
  - forwarded headers (X-Forwarded-For / Proto, Host handling).
- **S1 task lifecycle with side effects** (integration/scenarios): create -> Kafka `task_created` envelope -> MailHog email with the unique title -> WireMock received the webhook; start/complete -> `task_updated` and the webhooks. Collect the `Idempotency-Key` of all webhooks of one task and characterise it (the dispatcher uses `payload.id`, so created/updated share one key: BUG candidate, assert the observed behaviour in the test body).
- **S2a webhook retry**: WireMock scenario 503, 503, 200 -> delivered after retries (short `WEBHOOK_BACKOFF_BASE`); assert the journal count for the own payload.id.
- **S2b permanent failure -> DLQ -> scheduler replay** (`slow`): 4xx/5xx exhausted -> `webhook_dlq` message -> replay hits WireMock (no `Idempotency-Key` on the replay).
- **S3 inbound path**: simulator `/trigger-event` -> gateway -> receiver -> `webhook_inbound` envelope.

### T2 (not planned, and why)

- Every service `/health` through the gateway and `/metrics` series after traffic: smoke covers reachability.
- Separate S4 "idempotent duplicate delivery": folded into S1 (key characterisation); the simulator's dedupe is a component test.
- Redis paused -> API still works: component test (Redis down falls through to DB).
- Per-service functional tests over the network: duplicates of component tests.

