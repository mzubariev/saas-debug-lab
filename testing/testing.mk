# Test kit targets. Included from the repo-root Makefile.
TESTING_DIR := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))

SERVICES := task-service auth-service api-gateway webhook-receiver \
	external-service-simulator webhook-dispatcher notification-worker scheduler-worker

# Published by testing/compose.deps.yml. Override in the environment when CI injects them.
TEST_PG_URL ?= postgresql://postgres:test@localhost:5432/postgres
TEST_REDIS_URL ?= redis://localhost:6379
TEST_KAFKA_BOOTSTRAP ?= localhost:9092
export TEST_PG_URL TEST_REDIS_URL TEST_KAFKA_BOOTSTRAP

LAYER ?= unit
UV_RUN ?= uv run

# xdist workers per layer for t-gate (override with N=...). Integration and UI share one stack, so they stay low.
N_unit := auto
N_contract := auto
N_component := auto
N_integration := 3
N_e2e_ui := 2
N_smoke := 0
N_synthetic := 0
GATE_N = $(or $(N),$(N_$(LAYER)),auto)

.PHONY: t-unit t-component t-component-all deps-up deps-down deps-clean \
	t-contract contracts-update t-int t-ui t-smoke t-synthetic \
	t-lint t-check t-gate stack-up stack-down

t-unit:
	cd $(TESTING_DIR) && uv run pytest tests/unit -n auto --maxprocesses=8 -q

# One service per session. `uv sync --group <svc>` installs that group.
# t-component-all sets SKIP_SYNC=1 after one `uv sync --all-groups`.
# N overrides xdist workers (default auto). Run "make deps-up" first.
t-component:
	@test -n "$(SERVICE)" || (echo "Usage: make t-component SERVICE=task-service" >&2; exit 1)
	cd $(TESTING_DIR) && $(if $(SKIP_SYNC),:,uv sync --group $(SERVICE))
	cd $(TESTING_DIR) && $(UV_RUN) pytest tests/component --service $(SERVICE) -n $(or $(N),auto) --maxprocesses=8 -q$(if $(ALLOW_NO_TESTS), || [ $$? -eq 5 ])

# Sync once, then run the services in parallel without letting each uv run re-sync the environment.
# ALLOW_NO_TESTS: a service with no component tests yet exits 5; that is not a failure here.
t-component-all:
	cd $(TESTING_DIR) && uv sync --all-groups
	printf '%s\n' $(SERVICES) | xargs -P 4 -I{} $(MAKE) t-component SERVICE={} UV_RUN="uv run --no-sync" SKIP_SYNC=1 ALLOW_NO_TESTS=1

deps-up:
	docker compose -f $(TESTING_DIR)/compose.deps.yml up -d --wait

deps-down:
	docker compose -f $(TESTING_DIR)/compose.deps.yml down -v

deps-clean:
	docker compose -f $(TESTING_DIR)/compose.deps.yml exec -T postgres \
		psql -U postgres -d postgres -v ON_ERROR_STOP=1 -f - \
		< $(TESTING_DIR)/scripts/drop_stale_databases.sql

# SERVICE is required for tests/contract/http (one service per session); contract/events may run without it.
t-contract:
	cd $(TESTING_DIR) && uv run pytest tests/contract $(if $(SERVICE),--service $(SERVICE)) -n auto --maxprocesses=8 -q

# Rewrites committed snapshots (ADR-17). Tests read --update-contracts.
contracts-update:
	cd $(TESTING_DIR) && uv run pytest tests/contract $(if $(SERVICE),--service $(SERVICE)) -q --update-contracts

t-int:
	cd $(TESTING_DIR) && uv run pytest tests/integration -n 3 --dist loadgroup -q

stack-up:
	cd $(TESTING_DIR) && uv run python -c "from saas_testkit.infra import stack_up; stack_up()"

stack-down:
	cd $(TESTING_DIR) && uv run python -c "from saas_testkit.infra import stack_down; stack_down()"

t-ui:
	cd $(TESTING_DIR) && uv run pytest tests/e2e_ui -n 2 -q --tracing retain-on-failure --screenshot only-on-failure --video off

t-smoke:
	cd $(TESTING_DIR) && uv run pytest tests/smoke -n 0 -q

t-synthetic:
	cd $(TESTING_DIR) && uv run pytest tests/synthetic -n 0 -q

t-lint:
	cd $(TESTING_DIR) && uv run ruff check . && uv run ruff format --check . && uv run pyright

t-check: t-lint
	cd $(TESTING_DIR) && uv run pytest tests/unit -q -n 0

# Three runs, a fresh random order each time (pytest-randomly picks a new seed per run).
# make t-gate LAYER=component SERVICE=task-service
# component and contract need SERVICE (one service per pytest session); -n comes from N_<layer>.
t-gate:
	@set -eu; \
	case "$(LAYER)" in component|contract) \
		if [ -z "$(SERVICE)" ]; then echo "t-gate LAYER=$(LAYER) needs SERVICE=<name> (one service per session)" >&2; exit 1; fi;; \
	esac; \
	cd $(TESTING_DIR); \
	service_arg=""; \
	if [ -n "$(SERVICE)" ]; then service_arg="--service $(SERVICE)"; fi; \
	i=1; \
	while [ "$$i" -le 3 ]; do \
		uv run pytest tests/$(LAYER) $$service_arg -n $(GATE_N) --maxprocesses=8 -q || exit 1; \
		i=$$((i + 1)); \
	done
