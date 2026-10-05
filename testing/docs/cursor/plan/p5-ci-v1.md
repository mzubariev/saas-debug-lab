# P5: CI v1
Attach: `design/arch-ci.md` (sections 9 and 9.2 only).

Must do: create `.github/workflows/ci.yml` with these jobs:
- `lint`, `security` (ruff `S`, pip-audit, gitleaks) and `unit`.
- `component-contract`, a matrix over the services. It declares service containers for Postgres, Redis and Redpanda (Redpanda with a `command`, see section 9.2), sets `TEST_KAFKA_BOOTSTRAP`, `TEST_PG_URL`, `TEST_REDIS_URL` and `SCHEMA_EXAMPLES=40`, and uploads coverage and JUnit artifacts.
- `ci-gate`, built with the idiom from section 9.2: `if: always()` plus a `toJSON(needs)` check with `jq` that accepts `success` and `skipped`.

Also: use `concurrency` with cancel-in-progress, the `astral-sh/setup-uv` cache, a JUnit upload and a job summary. Triggers are `pull_request`, `push` to main (there is no merge queue on personal repositories) and `schedule` for the nightly run. Pin third-party actions by commit SHA (use `pinact` or Dependabot; never invent SHAs), set `permissions: contents: read`, set `timeout-minutes` on every job, use `uv sync --locked`, and do not add `merge_group` or a GHCR push. The Postgres service container uses the same major version as the lab and the test tuning (ADR-18).

Definition of done: push a branch and the pull request is green; break a test on purpose and the gate turns red; revert.
