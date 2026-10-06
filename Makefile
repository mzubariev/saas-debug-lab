# SaaS Debug Lab — common tasks (run from repo root)
# k6: load-tests/README.md | chaos: chaos/README.md

.PHONY: load-baseline load-chaos load-spike load-retry-storm load-concurrency load-slow-clients
.PHONY: break-kafka break-redis slow-db kill-worker chaos-scenario chaos-random
.PHONY: cache-stampede kafka-backlog retry-storm

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

# ─── Chaos (Part 2 — primitives / scenarios; see chaos/README.md) ────────────

break-kafka:
	docker stop kafka

break-redis:
	docker stop redis

slow-db:
	bash chaos/primitives/slow_db.sh

kill-worker:
	docker stop notification-worker

cache-stampede:
	bash chaos/scenarios/cache_stampede.sh

kafka-backlog:
	bash chaos/scenarios/kafka_backlog.sh

retry-storm:
	bash chaos/scenarios/retry_storm.sh

chaos-scenario:
	@test -n "$(SCENARIO)" || (echo "Usage: make chaos-scenario SCENARIO=kafka_lag" >&2; exit 1)
	bash chaos/runner.sh $(SCENARIO)

chaos-random:
	bash chaos/random_scenario.sh

# Test kit targets live in testing/testing.mk.
include testing/testing.mk
