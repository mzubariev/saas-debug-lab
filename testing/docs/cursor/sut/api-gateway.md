# api-gateway (SUT facts)

Directory `services/core/api-gateway`. Entrypoint `app.main:app` (uvicorn `:8000`, not published). No startup handler. Import calls `setup_logging`, `setup_sentry_fastapi` (`httpx=True`), `setup_telemetry`, then constructs `httpx.AsyncClient(timeout=gateway_timeout)` in `app/infrastructure/http/client.py`. That client is never closed.

Routes in `app/api/routes/proxy.py` (no response models). OpenAPI paths: `GET,POST,PUT,DELETE /auth/{path}`; `GET,POST,PUT,PATCH,DELETE /tasks` and `/tasks/{path}`; `GET,POST,PUT,PATCH,DELETE /webhooks/{path}`; plus `/health` and `/ready`. `/tasks` and `/tasks/{path}` depend on `verify_token` (`HTTPBearer`, `auto_error=False`). `/auth/*` and `/webhooks/*` do not. Proxy drops headers `host`, `sentry-trace`, `baggage`, `traceparent`, `tracestate`. `CORSMiddleware` allows `http://localhost:5173`, `http://127.0.0.1:5173`, and `http://localhost`. Downstream timeout → 504 `Downstream timeout`. Other `httpx.RequestError` → 502 `Downstream unavailable`. Upstream status and body are passed through. Compose healthcheck: Python `urllib` `GET http://localhost:8000/health` (this image has no curl).

Common facts (nginx, JWT, envelope, settings, timings, readiness, hazards): `testing/docs/cursor/sut/SUT_MAP.md`.
