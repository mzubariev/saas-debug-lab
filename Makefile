# SaaS Debug Lab — common tasks (run from repo root)
# k6 load tests: see load-tests/README.md

.PHONY: load-baseline load-chaos load-spike load-retry-storm load-concurrency load-slow-clients

load-baseline:
	k6 run load-tests/scripts/baseline.js

load-chaos:
	k6 run load-tests/scripts/chaos_mode.js

load-spike:
	k6 run load-tests/scripts/spike_traffic.js

load-retry-storm:
	k6 run load-tests/scripts/retry_storm.js

load-concurrency:
	k6 run load-tests/scripts/concurrency.js

load-slow-clients:
	k6 run load-tests/scripts/slow_clients.js
