# P1 - Infra core + first slice (strongest model; Plan/Ask first, then Agent)
Attach: arch-adr.md, arch-core-infra.md, arch-adapters-factories.md, SUT_MAP.md.
1. src/saas_testkit/config (settings.py, services.py), context.py, polling.py, infra/{containers,template_db,app_loader,xdist}.py (Testcontainers Postgres with the ADR-18 flags + tmpfs), root conftest.py (markers by path, --service, controller infra, pytest_configure_node, needs_infra, ignore other services), tests/component/conftest.py (worker_db, session_maker, db, service_env, flush_redis, clean_db, Redpanda/KafkaEventReader), template DB with touched-table tracking (arch-core-infra.md §6.2).
2. Domain models for tasks/users/envelope, concrete HttpTaskApi, TaskLifecycle flow, TaskCreateFactory (Polyfactory ModelFactory), TaskRowFactory (SQLAlchemyFactory) and the rows fixture binding row factories to the test session (create_async).
3. tests/component/task_service/conftest.py (service_app with lifespan, client; no get_db override: the app builds its engine from env) + two tests: create_task_returns_created_status, unknown_task_returns_404.
4. tests/unit self-tests: eventually, unique_title, factories.
DoD: `make t-component SERVICE=task-service` passes with -n 0 and -n 3, 3x in a row, DB-per-worker visible (test_task_service_component_gw0, ..._gw1); second run reuses the template (no Alembic re-run, check log); `pytest tests/unit` needs no Docker (docker stop all, still green); ruff + pyright clean.
Time-box: app loading / DI seam problem unresolved after 30 min -> fallback in arch-core-infra.md §6.4 and arch-quality.md §11.
Review yourself carefully: this is the heart of the kit.
