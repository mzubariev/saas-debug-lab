# external-service-simulator (SUT facts)

Directory `services/external/external-service-simulator`. No startup handler, no database, Redis, or Kafka. Host port `8000:8000`. In-memory set `_processed_keys` lives in the process.

| Method | Path | Request | Behaviour |
| --- | --- | --- | --- |
| POST | `/receive-webhook` | JSON object (free-form). Query `fail_rate` 0..1, `delay` ≥ 0, `status` int, all optional | `Idempotency-Key` already stored → 200 `{"status":"duplicate","idempotency_key":...}` before delay. Else sleep `delay`, then `random.random() < fail_rate` → 500 `{"status":"error","reason":"simulated_failure"}` (key not stored). Else non-200 `status` → that code `{"status":"custom_status","code":...}` (key not stored). Else 200 `{"status":"received","payload":...}` and the key is stored. Defaults from settings: fail 0.0, delay 0.0, status 200. |
| POST | `/trigger-event` | `InboundTrigger` `event`, `data` default `{}`. Query `retry` default 0, `delay` default 1.0 | 202 `{"status":"triggered","event":...}` immediately. Background `httpx.AsyncClient.post` to `integration_service_webhook_url`. |

Compose healthcheck curls `:8000/health`. No `depends_on`.

Common facts (nginx, JWT, envelope, settings, timings, readiness, hazards): `testing/docs/SUT_MAP.md`.
