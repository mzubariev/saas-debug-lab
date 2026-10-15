# auth-service (SUT facts)

Directory `services/core/auth-service`. Import builds `create_async_engine(postgres_dsn)` and calls `setup_telemetry` plus `instrument_sqlalchemy_async_engine`. No connection until the engine is used. The lifespan calls `start_redis` (`app.state.redis`). Shutdown stops Redis, then disposes the engine.

| Method | Path | Request | Response | Auth |
| --- | --- | --- | --- | --- |
| POST | `/auth/token` | `application/x-www-form-urlencoded` `OAuth2PasswordRequestForm` (`username`, `password`). Schema `Body_login_auth_token_post` | `TokenResponse` `access_token`, `token_type` default `bearer` (`app/schemas/auth.py`) | none |
| GET | `/auth/me` | `OAuth2PasswordBearer` tokenUrl `/auth/token` | `UserInfo` `username`, `role` | Bearer. Decode only; no database read |

DI: `get_db` yields `SessionLocal` (`app/dependencies.py`). `AuthServiceDep` builds `AuthService(db, request.app.state.redis)`. Passwords: passlib argon2 (`app/security.py`). A NUL byte in the username is 422 before the query. The cache write runs only after the password check succeeds. A wrong password leaves no `user:{username}` key. The stored JSON is still `username`, `hashed_password`, and `role`. Compose healthcheck: `curl -f http://localhost:8000/health`. Depends on postgres, redis, and migrations completed.

Common facts (nginx, JWT, envelope, settings, timings, readiness, hazards): `testing/docs/cursor/sut/SUT_MAP.md`.
