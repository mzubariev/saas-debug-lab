# task-service (SUT facts)

Directory `services/core/task-service`. Same async engine-at-import pattern as auth (`postgresql+asyncpg`). The lifespan connects Kafka (`AIOKafkaProducer.start`, `app.state.kafka`) then Redis. Shutdown stops Redis, then Kafka, then disposes the engine. No JWT check in this service.

Routes `app/api/routes/tasks.py`, models `app/schemas/task.py` (`TaskCreate.title` is `Field(min_length=1, max_length=255)`; `TaskOut` id/title/status/created_at/updated_at). An empty title, a title longer than 255, a NUL byte, and a lone surrogate are 422. Migration 0002 leaves `tasks.title` unbounded. OpenAPI: `GET,POST /tasks`, `GET /tasks/{task_id}`, `PATCH /tasks/{task_id}/start`, `PATCH /tasks/{task_id}/complete`. `POST /tasks` is 201. DI: `get_db`; `get_task_service` passes `app.state.redis` and `app.state.kafka`. Repository commits inside `create` and `save`.

Transitions: `start` only from `created`, `complete` only from `in_progress`. Else 409 `Cannot start task in status '{status}'. Expected 'created'.` or the complete equivalent with `in_progress`. Missing row: 404 `Task not found`. A cache hit returns the stored JSON dict; a miss returns the ORM row. `response_model` is `TaskOut` either way. Publish happens after the DB commit, then the list key (and the item key on transition) is deleted. A Kafka failure after that commit returns 500 and leaves the row (BUG-3): a create stays stored, a start stays `in_progress`, the event is not published, and the cache delete does not run. Compose healthcheck curls `:8000/health`. Depends on postgres, kafka, redis, migrations.

Common facts (nginx, JWT, envelope, settings, timings, readiness, hazards): `testing/docs/cursor/sut/SUT_MAP.md`.
