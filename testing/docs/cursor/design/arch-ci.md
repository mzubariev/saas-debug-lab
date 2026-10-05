# Testing architecture: CI/CD (GitHub Actions) and scaling (P5, P9)
Playwright in CI: §9.3. Grafana SM: cat-smoke-synthetic.md. The placeholders `<SHA>` and `<pinned-version>` in the YAML must be resolved before use (pinact or Dependabot for SHAs; never invent them).

## 9. CI design
DAG on push/PR: lint (ruff, pyright), security (ruff S, audit, gitleaks), unit (xdist) -> component-contract (matrix: service; services: postgres, redis, redpanda) ; integration (builds images in-job, buildx gha cache) ; ui-e2e (own stack, same cache) ; all -> ci-gate (only required check).
- concurrency cancel-in-progress; cheap jobs block expensive ones (needs).
- Required status check = ci-gate only. It must use `if: always()` and inspect toJSON(needs) (§9.2): otherwise a failed or skipped dependency leaves the gate itself skipped, which GitHub counts as passing.
- Env-driven: component job sets TEST_PG_URL, TEST_REDIS_URL, SCHEMA_EXAMPLES; integration/ui set BASE_URL. Same pytest command as local.
- GitHub Actions supports command/entrypoint inside services:, so Redpanda is a plain service container (YAML in §9.2; pin the version, verify flags against the Redpanda docs for that version). The job sets TEST_KAFKA_BOOTSTRAP=localhost:9092 and polls the broker before pytest.
- Integration/UI: `docker compose ... up -d --wait` (buildx layer cache via docker/bake-action, or --build with gha cache), pytest -n 3; on failure upload docker compose logs, Playwright test-results/ (traces, screenshots), JUnit.
- Cadence: PR = lint/security/unit/component/contract(light)/integration(fast subset)/UI -m critical. Push to main = everything except deep fuzz + cross-browser (merge queue is not available for personal-account repos; check Settings -> Rules). Nightly = Schemathesis deep+stateful, firefox/webkit, chaos + slow markers, flaky report (--count 5 on tests with reruns), refresh .test_durations. smoke.yml after build/deploy against SMOKE_BASE_URL (blocks).
- synthetic.yml is written with cron */5 (API) / */30 (browser) against SYNTHETIC_BASE_URL and an issue after 3 consecutive failures, but ships dormant (workflow_dispatch only): GitHub runners and Grafana public probes cannot reach a local lab, and a tunnel would expose admin/admin123. Enable the cron only when a reachable URL exists (GitHub cron is best-effort anyway). For the local lab: make synthetic-local (loop every 5 min) and/or the Grafana private probe (cat-smoke-synthetic.md).
- Reports: JUnit XML per job -> $GITHUB_STEP_SUMMARY (dorny/test-reporter); coverage per service (`[tool.coverage.run] parallel = true`, `concurrency = ["thread", "greenlet"]`, `sigterm = true`, because async SQLAlchemy runs ORM internals in greenlets) combined in a coverage job (coverage combine; report only until service unit tests exist, then add a threshold); reruns are listed, not hidden.
- "Trace coverage" is not a standard metric: replaced by API coverage (httpx event hook logs method + route template; a meta-test compares against each service's OpenAPI operations, reported as %).
- Sharding (pytest-split --splits N --group k) is wired in the matrix from day one with shards: [1]; raise only when integration+UI exceeds ~8 min (§12).
- Deploy step: out of scope for the lab (no target server); smoke.yml and synthetic.yml run against any URL.

### 9.2 `ci.yml` skeleton (P5; adapt names to SUT_MAP, resolve action SHAs)

Differences from the usual boilerplate, on purpose: no `merge_group` (no merge queue on personal repos), no image build/push to GHCR (integration builds inside the job, P9), service containers include Redis and Redpanda, `uv sync --locked` (fails when `uv.lock` is stale; `--frozen` would hide it), every third-party action pinned by commit SHA, `permissions` minimal, `timeout-minutes` on every job.

```yaml
name: ci

on:
  pull_request:
  push:
    branches: [main]
  schedule:
    - cron: "0 2 * * *"            # nightly; heavy suites move to nightly.yml in P9

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

permissions:
  contents: read

defaults:
  run:
    working-directory: testing

jobs:
  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@<SHA>            # vX
      - uses: astral-sh/setup-uv@<SHA>          # vX
        with: { enable-cache: true, cache-dependency-glob: testing/uv.lock }
      - run: uv sync --locked
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run pyright

  security:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions: { contents: read, pull-requests: read }
    steps:
      - uses: actions/checkout@<SHA>            # vX
        with: { fetch-depth: 0 }                # gitleaks scans history
      - uses: astral-sh/setup-uv@<SHA>          # vX
        with: { enable-cache: true, cache-dependency-glob: testing/uv.lock }
      - run: uv sync --locked
      - run: uv run ruff check --select S .
      - run: |
          uv export --locked --no-hashes --no-emit-project > /tmp/req.txt
          uv run pip-audit -r /tmp/req.txt --no-deps --disable-pip
      - uses: gitleaks/gitleaks-action@<SHA>    # vX
        env: { GITHUB_TOKEN: "${{ secrets.GITHUB_TOKEN }}" }

  unit:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@<SHA>            # vX
      - uses: astral-sh/setup-uv@<SHA>          # vX
        with: { enable-cache: true, cache-dependency-glob: testing/uv.lock }
      - run: uv sync --locked
      - run: uv run pytest tests/unit -n auto -q --junitxml=reports/junit-unit.xml
      - uses: actions/upload-artifact@<SHA>     # vX
        if: ${{ !cancelled() }}
        with: { name: junit-unit, path: testing/reports/junit-unit.xml }

  component-contract:
    needs: [lint, unit]                         # cheap jobs block expensive ones
    runs-on: ubuntu-latest
    timeout-minutes: 25
    permissions: { contents: read, checks: write }   # checks: write only for test-reporter
    strategy:
      fail-fast: false
      matrix:
        service: [task-service, auth-service, api-gateway, webhook-receiver, external-service-simulator]
    env:
      TEST_PG_URL: postgresql://postgres:test@localhost:5432/postgres
      TEST_REDIS_URL: redis://localhost:6379
      TEST_KAFKA_BOOTSTRAP: localhost:9092
      SCHEMA_EXAMPLES: ${{ github.event_name == 'schedule' && '500' || '40' }}
      COVERAGE_FILE: .coverage.${{ matrix.service }}
    services:
      postgres:
        image: postgres:15                      # same major as the lab (infra/docker-compose.yml); one pinned tag in compose.deps.yml, Testcontainers and CI
        env: { POSTGRES_PASSWORD: test }
        command: postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off -c max_connections=200
        options: >-
          --tmpfs /var/lib/postgresql/data
          --health-cmd "pg_isready -U postgres" --health-interval 5s --health-timeout 5s --health-retries 10
        ports: ["5432:5432"]
      redis:
        image: redis:7-alpine                   # pin
        options: >-
          --health-cmd "redis-cli ping" --health-interval 5s --health-timeout 5s --health-retries 10
        ports: ["6379:6379"]
      redpanda:
        image: docker.redpanda.com/redpandadata/redpanda:<pinned-version>
        command: >-
          redpanda start --mode dev-container --smp 1 --memory 1G --overprovisioned
          --kafka-addr plaintext://0.0.0.0:9092 --advertise-kafka-addr plaintext://localhost:9092
        ports: ["9092:9092"]
    steps:
      - uses: actions/checkout@<SHA>            # vX
      - uses: astral-sh/setup-uv@<SHA>          # vX
        with: { enable-cache: true, cache-dependency-glob: testing/uv.lock }
      - run: uv sync --locked --group ${{ matrix.service }}
      - id: svc                                 # service directory comes from config/services.py (services/core/..., workers/...)
        run: echo "path=$(uv run python -c 'from saas_testkit.config.services import SERVICES; print(SERVICES["${{ matrix.service }}"].path)')" >> "$GITHUB_OUTPUT"
      - name: Wait for Redpanda
        run: timeout 60 bash -c 'until (echo > /dev/tcp/localhost/9092) 2>/dev/null; do sleep 1; done'
      - run: >-
          uv run pytest tests/component tests/contract --service ${{ matrix.service }}
          -n auto -q --cov=../${{ steps.svc.outputs.path }} --cov-report=
          --junitxml=reports/junit-${{ matrix.service }}.xml
      - uses: actions/upload-artifact@<SHA>     # vX
        if: ${{ !cancelled() }}
        with:
          name: reports-${{ matrix.service }}
          path: |
            testing/reports/junit-${{ matrix.service }}.xml
            testing/.coverage.${{ matrix.service }}
          include-hidden-files: true
      - uses: dorny/test-reporter@<SHA>         # vX
        if: ${{ !cancelled() }}
        with:
          name: junit-${{ matrix.service }}
          path: testing/reports/junit-${{ matrix.service }}.xml
          reporter: java-junit

  ci-gate:                                      # the ONLY required status check
    if: always()                                # without it a failed need makes the gate "skipped" = green
    needs: [lint, security, unit, component-contract]   # P9 appends integration, smoke, ui-e2e, coverage
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - name: Every needed job succeeded or was legitimately skipped
        env:
          NEEDS: ${{ toJSON(needs) }}
        run: echo "$NEEDS" | jq -e 'all(.[]; .result == "success" or .result == "skipped")'
```

Notes: `skipped` is accepted because path filters, PR-only or main-only jobs are skipped legitimately; `failure`, `cancelled` and anything else fail the gate. Pass `needs` through `env`, never interpolate it into the script. When a job is added to the DAG it must also be added to the gate's `needs`. Resolve SHAs with Dependabot or `pinact` instead of typing them by hand; verify `command` / `options` support for service containers and image data-dir paths against current GitHub and image docs.

### 9.3 Playwright in CI (`ui-e2e`, P9)

The job runs the compose stack on the runner host, so a job-level container (`mcr.microsoft.com/playwright/python:v<version>-noble`) would need host networking and Docker access: use the browser cache instead.

```yaml
      - id: pw
        run: echo "version=$(uv run python -c 'from importlib.metadata import version; print(version("playwright"))')" >> "$GITHUB_OUTPUT"
      - id: pw-cache
        uses: actions/cache@<SHA>               # vX
        with:
          path: ~/.cache/ms-playwright
          key: pw-${{ runner.os }}-${{ steps.pw.outputs.version }}
      - if: steps.pw-cache.outputs.cache-hit != 'true'
        run: uv run playwright install --with-deps chromium    # browser + OS libraries
      - if: steps.pw-cache.outputs.cache-hit == 'true'
        run: uv run playwright install-deps chromium           # cache holds browsers only, not apt packages
```

- The cache key is the Playwright version: a bump downloads the new browsers, old ones expire.
- Nightly cross-browser: add `firefox webkit` to the install commands and include the browser in the key.
- If a container job is ever preferred (UI against an already running remote URL), the image tag must equal the installed Playwright version.
- Why `-n 2`: one Chromium process per worker costs roughly 300-500 MB, plus pages and traces, and it competes for CPU with the whole compose stack (Postgres, Kafka, a dozen services) on the same runner. Two workers keep the run inside a standard runner's RAM/CPU with headroom; raise `-n` only after measuring (§12), and scale out with shards rather than workers.
- On failure upload `test-results/` (trace, screenshot) and `docker compose logs`.

## 12. Scaling model
- Scale-up (vertical, inside one stack copy): more xdist workers. component/contract -n auto (DB per worker from a shared template); integration -n 3; e2e_ui -n 2 (browser per worker, context per test).
- Scale-out (horizontal, many stack copies): CI matrix. component/contract: one job per service. integration/e2e_ui: shard: [1..N] with pytest-split --splits N --group k --durations-path .test_durations; every shard brings up its own compose stack, seeds it and logs in on its own; JUnit/coverage artifacts are merged in the gate job.
- Why scale-out needs no coordination: all data is unique (uuid / run prefix), nothing is cleaned by default (clean_db is per-stack and on demand), no shared mutable state between stacks, auth/seed is per stack.
- Limits of scale-up: one stack's Kafka/PG/nginx and the runner's CPU/RAM (browsers are the heaviest). Hence conservative -n for integration/UI.
- When to scale: keep shards: [1] while integration+UI < ~8 min; first raise -n (cheap), then shards (more runners, more image builds, more minutes).
- Hands-on experiment (record numbers in README): run the integration suite with -n 1, 2, 4 on the same stack and note wall time and failures; then two shards in CI (shard: [1, 2]) and compare. Expect sub-linear gains from -n (shared stack) and near-linear from shards (independent stacks, minus build/boot overhead). Refresh .test_durations nightly so shards stay balanced.
