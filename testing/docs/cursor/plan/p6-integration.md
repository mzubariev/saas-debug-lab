# P6: Integration stack and tests
Attach: `design/arch-integration.md`, `SUT_MAP.md`, `KIT_MAP.md` and the `sut/<service>.md` files of the services a scenario touches.

## P6.0: KRaft migration of the lab's Kafka (separate branch, before P6.1; use a strong model)
Replace cp-kafka plus ZooKeeper with a single KRaft node (keep the existing external listener `PLAINTEXT_HOST://localhost:9093`, which the test override publishes; broker and controller roles, `CLUSTER_ID`, `controller.quorum.voters`, separate internal and external listeners) and remove the zookeeper service. This is infrastructure only, with no production code changes. Preserve the existing network settings, and make sure `kafka-exporter`, `kafka-ui` (if present) and the Python services still reach Kafka on the correct internal ports. Old ZooKeeper-era volumes are incompatible with KRaft, so drop them.

Do it now because it removes a container and shortens the integration-stack boot, which pays back through P6 to P9. It does not affect P0 to P5, because component and contract tests use Redpanda.

Definition of done: the whole lab works as before (manual smoke: login, create a task, move a task, email in MailHog, webhook delivered) and `kafka-exporter` sees the broker. Time-box: if it takes more than about two hours, run `git restore` and keep ZooKeeper for now; the item stays in F.4 of `p10-polish-after.md`.

## P6.1 (strong model): the stack and its helpers
Must do: create `infra/docker-compose.test.yml` with the gateway published on `:8001`, and Postgres, Redis, the Kafka external listener `localhost:9093` and the workers' metrics ports (for example 9101 dispatcher, 9102 notification, 9103 scheduler) published on the host, because the base compose keeps them internal and seeding, `KafkaEventReader` and readiness checks run from the host (the scheduler binds its metrics port in one prefork child only, so poll it with retries), WireMock, `WEBHOOK_URL` of both the dispatcher and the scheduler pointing at WireMock, the timing knobs, and Postgres with the ADR-18 `command` and tmpfs; nginx is not relaxed. Define the explicit service list. Implement `src/saas_testkit/infra/compose.py` with `BASE_URL` (environment or bring-up) and `KEEP_STACK`, and with readiness checked per service kind (FastAPI `/health`, workers `:9100/metrics`, migrations exit code 0, a hard timeout and `docker compose logs --tail` on failure). Seed and log in once per run (FileLock, token file with an expiry check). Add the adapters (Kafka reader, MailHog, WireMock, the real-network `HttpTaskApi` and `HttpAuthApi`) and `tests/integration/conftest.py`. Update `KIT_MAP.md`.

Definition of done: `make stack-up` is healthy; one test (login, create a task, read the task) is green with `-n 3`; `KIT_MAP.md` lists the integration fixtures.

## P6.2 integration/services
Cover health through the gateway, the auth to gateway to task JWT flow, the nginx edge tests (dedicated, marked `@pytest.mark.xdist_group("serial")`, run with `--dist loadgroup`; send about 10 logins within a minute and expect no 429, because nginx does not account requests with an empty zone key; if confirmed, record BUG-1), and the `/metrics` series.

## P6.3 integration/scenarios
Write S1, S3 and S4 first (they are fast). Mark S2 as `slow` and S5 as `chaos`.

Definition of done for P6.2 and P6.3: `make t-int` is green twice, no test uses `sleep`, all data is unique, and the suite works with `KEEP_STACK=1`.
