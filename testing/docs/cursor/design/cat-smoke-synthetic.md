# Test catalogue: smoke and synthetic (P8), Grafana SM stretch

Tiers: T1 = must, T2 = if time, T3 = not planned. Smoke owns reachability of everything (so integration does not repeat it); synthetic owns one continuous critical path.

## Smoke (post-deploy gate, 1-2 min, broad, T1)

About 6 tests: /health of every service through the gateway (one parametrized test); login for both roles; create + read one task; /metrics reachable; frontend returns 200. Reads SMOKE_BASE_URL. Any failure blocks the pipeline/rollback. Wrong URL -> fails fast with a clear message.

## Synthetic (continuous, narrow, API-first)

- T1 api/: ONE test: gateway health -> login (synthetic user) -> create task -> read -> start -> complete, with per-step latency budgets (soft warn, hard fail).
- T3 browser: (optional/discussable) (one more moving part for little extra signal; the UI is covered by e2e_ui).
- Requirements: dedicated synthetic user (from env), X-Synthetic: true header, titles prefixed synthetic- (scheduler cleanup removes completed), non-destructive, respects nginx limits, no secrets in logs, fail only after 3 consecutive failures (alert on the streak), JUnit + step-level timings in job summary. Reads SYNTHETIC_BASE_URL.
- Same flows/adapters as other layers; policy differs: smoke blocks a pipeline, synthetic alerts and never blocks. `synthetic.yml` ships dormant (workflow_dispatch only); `make synthetic-local` loops every 5 minutes.



## Grafana Cloud Synthetic Monitoring (T2 stretch)

- Free plan: 100k synthetic executions/month (verify on the pricing page). One check every 5 min from one location ~ 8.6k/month; each extra probe location multiplies it.
- Checks are k6-based (JS): a separate copy of the critical path, not the Python flows.
- The lab runs locally: use a private probe (Synthetic Monitoring Agent in a container, outbound-only); avoid a tunnel (it would expose admin/admin123).
- Script: testing/synthetic/k6/critical_path.js (reuse load-tests/lib/helpers.js); add an alert rule and a dashboard.

