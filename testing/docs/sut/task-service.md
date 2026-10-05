# task-service (SUT facts)

Directory `services/core/task-service`. Same async engine-at-import pattern as auth (`postgresql+asyncpg`). Startup connects Kafka (`AIOKafkaProducer.start`, `app.state.kafka`) and Redis. Shutdown stops both. No JWT check in this service.

Routes `app/api/routes/tasks.py`, models `app/schemas/task.py` (`TaskCreate.title`, `TaskOut` id/title/status/created_at/updated_at). OpenAPI: `GET,POST /tasks`, `GET /tasks/{task_id}`, `PATCH /tasks/{task_id}/start`, `PATCH /tasks/{task_id}/complete`. `POST /tasks` is 201. DI: `get_db`; `get_task_service` passes `app.state.redis` and `app.state.kafka`. Repository commits inside `create` and `save`.

Transitions: `start` only from `created`, `complete` only from `in_progress`. Else 409 `Cannot start task in status '{status}'. Expected 'created'.` or the complete equivalent with `in_progress`. Missing row: 404 `Task not found`. A cache hit returns the stored JSON dict; a miss returns the ORM row. `response_model` is `TaskOut` either way. Publish happens after the DB commit, then the list key (and the item key on transition) is deleted. Compose healthcheck curls `:8000/health`. Depends on postgres, kafka, redis, migrations.

Common facts (nginx, JWT, envelope, settings, timings, readiness, hazards): `testing/docs/SUT_MAP.md`.
