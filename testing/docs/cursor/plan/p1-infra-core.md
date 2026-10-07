# P1: Infrastructure core and the first slice
Use a strong model, in Plan or Ask mode first, then Agent mode. This is the heart of the kit, so review it yourself.

Attach: `design/arch-adr.md`, `design/arch-core-infra.md`, `design/arch-adapters-factories.md`, `sut/SUT_MAP.md` and `sut/task-service.md`.

Must do:
1. Create `src/saas_testkit/config` (`settings.py`, `services.py`), `context.py`, `polling.py` and `infra/{containers,template_db,app_loader,xdist}.py`. The Testcontainers Postgres uses the ADR-18 flags and tmpfs. Create the root `conftest.py` (markers by path, `--service`, controller infrastructure, `pytest_configure_node`, `needs_infra`, ignoring other services' directories). Create `tests/component/conftest.py` with the fixtures `worker_db`, `session_maker`, `db`, `service_env`, `flush_redis`, `clean_db` and the Redpanda and `KafkaEventReader` wiring. Build the template database with touched-table tracking (`arch-core-infra.md` section 6.2). Use the same Postgres major version as the lab.
2. Add the domain models for tasks, users and the envelope, the concrete `HttpTaskApi`, the `TaskLifecycle` flow, `TaskCreateFactory` (Polyfactory `ModelFactory`), `TaskRowFactory` (`SQLAlchemyFactory`), and the `rows` fixture that binds row factories to the test's session (`create_async`). Seed the factories once per run from pytest-randomly's seed.
3. Create `tests/component/task_service/conftest.py` (`service_app` with lifespan, and `client`; do not override `get_db`, because the app builds its engine from the environment) and two tests: `test_create_task_returns_created_status` and `test_unknown_task_returns_404`.
4. Add `tests/unit` self-tests for `eventually`, `unique_title` and the factories.
5. Create `testing/docs/cursor/KIT_MAP.md` (30–50 lines: public fixtures, flows, factories, markers and make targets).

Definition of done:
- `make t-component SERVICE=task-service` passes with `-n 0` and with `-n 3`, three times in a row.
- The database per worker is visible (`test_task_service_component_gw0`, `..._gw1`), and a second run reuses the template (no Alembic re-run, check the log).
- `pytest tests/unit` needs no Docker (stop all containers and it is still green).
- ruff and pyright are clean, and `KIT_MAP.md` exists.

Time-box: if app loading or a missing DI seam is still unresolved after 30 minutes, use the fallback in `arch-core-infra.md` section 6.4 and `arch-quality.md` section 11.
