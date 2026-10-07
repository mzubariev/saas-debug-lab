# Testing architecture: security, flake policy, risks and fallbacks, anti-patterns

## 8. Security testing
- Static in CI: ruff (with S bandit rules), pip-audit / uv pip audit, gitleaks (free GitGuardian alternative), Trivy image scan (nightly).
- Functional (inside the suites): authN/authZ matrix, JWT tampering/expiry/alg=none, brute-force limit at nginx, injection-like strings in fields via Schemathesis, no secrets/hashes in responses or logs.
- Nightly stretch: OWASP ZAP baseline against the compose stack.

## 10. Flake and quality policy
--strict-markers, pytest-randomly, pytest-timeout (component 30 s, contract 120 s, integration 120 s, e2e_ui 120 s), --reruns 1 only for integration/e2e_ui and always reported; web-first assertions; no sleeps; every xfail is strict and linked to KNOWN_ISSUES.md. New tests must pass 3x with random order and -n auto.

## 11. Risks and fallbacks (decide within 30 min, then take the fallback)
- Python 3.14 wheels missing (unlikely as of 2026-10) -> venv on 3.13 (15 min, ADR-12).
- Service import has side effects -> the recon found only OTEL at import (a BatchSpanProcessor dialling OTLP_ENDPOINT); Kafka and Redis connect in startup only, Sentry is inert without a DSN. Fix without touching prod: service_env sets OTLP_ENDPOINT="" and SENTRY_DSN="". Only if that is not enough: PREP (P0.1) or monkeypatch before import. ddtrace is imported lazily by the first log line and is removed in P0.1 together with that import.