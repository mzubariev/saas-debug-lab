# Testing architecture: security, flake policy, risks and fallbacks, anti-patterns

## 8. Security testing
- Static in CI: ruff (with S bandit rules), pip-audit / uv pip audit, gitleaks (free GitGuardian alternative), Trivy image scan (nightly).
- Functional (inside the suites): authN/authZ matrix, JWT tampering/expiry/alg=none, brute-force limit at nginx, injection-like strings in fields via Schemathesis, no secrets/hashes in responses or logs.
- Nightly stretch: OWASP ZAP baseline against the compose stack.

## 10. Flake and quality policy
--strict-markers, pytest-randomly, pytest-timeout (component 30 s, integration 120 s), --reruns 1 only for integration/e2e_ui and always reported; web-first assertions; no sleeps; every xfail is strict and linked to KNOWN_ISSUES.md. New tests must pass 3x with random order and -n auto.

## 11. Risks and fallbacks (decide within 30 min, then take the fallback)
- Python 3.14 wheels missing -> venv on 3.13 (15 min, ADR-12).
- Service lifespan/import has side effects (Kafka/Redis connect, Sentry, ddtrace) -> PREP (P0.1): move them to startup, inert without env; only if impossible: monkeypatch before import / stub ddtrace in sys.modules.
- Service does not take DB/Redis/Kafka URLs from env -> PREP: make env-driven (default unchanged); else patch the module-level getter (ADR-14).
- Schemathesis from_asgi runs the app in a different event loop than async fixtures -> the app builds its own engine from env (default design); still failing -> from_url(BASE_URL) against the compose stack (time-box Schemathesis at 30 min).
- Alembic env.py cannot take a URL override -> Base.metadata.create_all for the template.
- Full-stack build too slow in CI -> build only the core services needed; cache layers; run integration on push to main + nightly, keep UI -m critical on PR.
- Test env lacks service runtime deps, or services pin conflicting versions -> uv dependency group per service; sync only the group of the service under test (uv sync --group <svc>); long-term fix = R0 (uv + pyproject per service).
- Nginx limits (UI tests) / seeded data conflicts -> functional tests use gateway :8001; UI: login once per run, fewer workers; do not relax nginx; assert only on own ids.

## 13. Anti-patterns (do not)
1. One container (or DB server) per xdist worker: the controller owns infra, workers read URLs (ADR-2).
2. A session-scoped Testcontainers fixture that ignores xdist: every worker starts its own copy. Start in the controller only.
3. Logging in through the UI in every test: API login once per run, storage_state for UI tests.
4. A shared mutable seed or shared mutable rows between tests, and asserting on totals of shared collections: unique data, assert on own ids.
5. sleep / wait_for_timeout: use eventually() and web-first assertions.
6. Global --reruns: only integration / e2e_ui, max 1, always reported; flakiness is measured nightly, not hidden.
7. docker compose build from scratch on every shard/job: buildx with the gha layer cache, build only the services under test.
8. SAVEPOINT-rollback sessions, get_db overrides or fake DB/Kafka implementations where the real thing is cheap (ADR-3, 4, 5).
9. Relaxing nginx limits, or sharing one login across parallel UI workers beyond the token file: functional tests use the gateway.
10. Kubernetes (or any orchestration) before compose + CI matrix stops being enough; speculative Protocols before a second implementation exists.
