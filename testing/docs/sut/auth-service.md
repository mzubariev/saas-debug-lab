# auth-service (SUT facts)

Directory `services/core/auth-service`. Import builds `create_async_engine(postgres_dsn)` and calls `setup_telemetry` plus `instrument_sqlalchemy_async_engine`. No connection until the engine is used. `@app.on_event("startup")` calls `start_redis` (`app.state.redis`); shutdown closes it.

| Method | Path | Request | Response | Auth |
| --- | --- | --- | --- | --- |
| POST | `/auth/token` | `application/x-www-form-urlencoded` `OAuth2PasswordRequestForm` (`username`, `password`). Schema `Body_login_auth_token_post` | `TokenResponse` `access_token`, `token_type` default `bearer` (`app/schemas/auth.py`) | none |
| GET | `/auth/me` | `OAuth2PasswordBearer` tokenUrl `/auth/token` | `UserInfo` `username`, `role` | Bearer. Decode only; no database read |

DI: `get_db` yields `SessionLocal` (`app/dependencies.py`). `get_auth_service` builds `AuthService(db, request.app.state.redis)`. Passwords: passlib argon2 (`app/security.py`). Cache JSON stores `username`, `hashed_password`, `role`. Compose healthcheck: `curl -f http://localhost:8000/health`. Depends on postgres, redis, and migrations completed.

Common facts (nginx, JWT, envelope, settings, timings, readiness, hazards): `testing/docs/SUT_MAP.md`.
