# Test catalogue: smoke and synthetic (P8), Grafana SM stretch

## Smoke (post-deploy gate, 1-2 min, broad)
/health of every service through the gateway; login for both roles; create + read one task; /metrics reachable; frontend returns 200. Reads SMOKE_BASE_URL. Any failure blocks the pipeline/rollback. Wrong URL -> fails fast with a clear message.

## Synthetic (continuous, narrow, API-first)
- api/: gateway health -> login (synthetic user) -> create task -> read -> start -> complete, with per-step latency budgets (soft warn, hard fail).
- browser/ (optional, every 30 min): UI login -> create card -> move.
- Requirements: dedicated synthetic user (from env), X-Synthetic: true header, titles prefixed synthetic- (scheduler cleanup removes completed), non-destructive, respects nginx limits, no secrets in logs, fail only after 3 consecutive failures (alert on the streak, not one blip), JUnit + step-level timings in job summary. Reads SYNTHETIC_BASE_URL.
- Same flows/adapters as other layers; policy differs: smoke blocks a pipeline, synthetic alerts and never blocks.

## Grafana Cloud Synthetic Monitoring (optional stretch, recommended continuous monitor for the local lab)
- Free plan: 100k synthetic executions/month (verify on the pricing page). One check every 5 min from one location ~ 8.6k/month; each extra probe location multiplies it.
- Checks are k6-based (HTTP/multi-step/browser scripts in JS): a separate JS copy of the critical path, not the Python flows.
- The lab runs locally: use a private probe (Synthetic Monitoring Agent in a container, outbound-only, no public exposure) or a tunnel for public probes (a tunnel would expose admin/admin123: avoid).
- Script: testing/synthetic/k6/critical_path.js (reuse helpers from load-tests/lib/helpers.js); add alert rules and a dashboard. Interview value: continuous black-box SLI/SLO view next to the Python suite.
