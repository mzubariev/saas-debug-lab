# P6: Integration stack and tests
Attach: `design/arch-integration.md`, `SUT_MAP.md` and `KIT_MAP.md`.

## P6.1 (strong model): the stack and its helpers
Must do: create `infra/docker-compose.test.yml` with the gateway published on `:8001`, WireMock, `WEBHOOK_URL` of both the dispatcher and the scheduler pointing at WireMock, the timing knobs, and Postgres with the ADR-18 `command` and tmpfs; nginx is not relaxed. Define the explicit service list. Implement `src/saas_testkit/infra/compose.py` with `BASE_URL` (environment or bring-up) and `KEEP_STACK`, and with readiness checked per service kind (FastAPI `/health`, workers `:9100/metrics`, migrations exit code 0, a hard timeout and `docker compose logs --tail` on failure). Seed and log in once per run (FileLock, token file with an expiry check). Add the adapters (Kafka reader, MailHog, WireMock, the real-network `HttpTaskApi` and `HttpAuthApi`) and `tests/integration/conftest.py`. Update `KIT_MAP.md`.

Definition of done: `make stack-up` is healthy; one test (login, create a task, read the task) is green with `-n 3`; `KIT_MAP.md` lists the integration fixtures.

## P6.2 integration/services
Cover health through the gateway, the auth to gateway to task JWT flow, the nginx edge tests (dedicated, marked `@pytest.mark.xdist_group("serial")`, run with `--dist loadgroup`; the auth-burst test is characterised and will likely become BUG-1), and the `/metrics` series.

## P6.3 integration/scenarios
Write S1, S3 and S4 first (they are fast). Mark S2 as `slow` and S5 as `chaos`.

Definition of done for P6.2 and P6.3: `make t-int` is green twice, no test uses `sleep`, all data is unique, and the suite works with `KEEP_STACK=1`.
