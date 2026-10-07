# webhook-dispatcher (SUT facts)

Directory `services/core/webhook-dispatcher` (not `workers/`). No FastAPI app. Entry `python -m app.run` → `main()`. `main` calls `setup_logging`, `setup_worker_telemetry`, `setup_sentry_worker`, `start_http_server(metrics_port)`, then `_async_main` (producer, `httpx.AsyncClient`, consumer). Import of `app.run` does not do that; it does register Prometheus metrics because `consumer` imports `dispatcher_service`.

Consumer: `AIOKafkaConsumer` on `task_created` and `task_updated` (`CONSUME_TOPICS`, not env), `group_id` default `webhook-dispatcher`, `auto_offset_reset=earliest`. Each POST sends `Idempotency-Key` set to `str(payload.get("id", ""))`. Backoff base is `WEBHOOK_BACKOFF_BASE` (default 1.0). 4xx stops and writes the DLQ. 5xx and `httpx.RequestError` retry. Permanent failure produces to `webhook_dlq`. Produce errors are logged and swallowed. There is no compose healthcheck and no published port. Depends on kafka and external-service-simulator healthy. Readiness that exists in code is `GET /metrics` on `METRICS_PORT` after `main()` has started the server.

Common facts (nginx, JWT, envelope, settings, timings, readiness, hazards): `testing/docs/cursor/sut/SUT_MAP.md`.
