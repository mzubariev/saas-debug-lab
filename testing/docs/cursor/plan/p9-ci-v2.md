# P9: CI v2
Attach: `design/arch-ci.md` (the whole file: sections 9, 9.2, 9.3 and 12) and `KIT_MAP.md`.

Must do: extend `ci.yml` with these jobs.
- `integration`: build the needed images inside the job with buildx and the GitHub Actions cache, bring up an explicit service list, check readiness per service kind, set `BASE_URL`, run with `-n 3`, and upload logs as an artifact on failure.
- `smoke`: reuse `smoke.yml` after the stack is up; it blocks.
- `ui-e2e`: Playwright as described in section 9.3 (browser cache keyed by the Playwright version plus `install-deps`, `-n 2`, `-m critical` on pull requests, the full suite on push to main, traces as an artifact).
- A `coverage` job that combines the service coverage.
- `ci-gate` must need all jobs; append every new job to its `needs`.

Also add a shard matrix to `integration` and `ui-e2e` (`shard: [1]` by default, with `pytest-split --splits ${{ strategy.job-total }} --group ${{ matrix.shard }}` and a cached `.test_durations`), so scaling out is a one-line change (section 12). Add `nightly.yml`: Schemathesis with 500 examples, the `slow` and `chaos` markers, a firefox and webkit matrix, a `--count 5` flaky pass, and a refresh of `.test_durations`.

Definition of done: a pull request runs the full DAG green, `needs` prevents the e2e job from running when lint fails, and the artifacts are downloadable.
