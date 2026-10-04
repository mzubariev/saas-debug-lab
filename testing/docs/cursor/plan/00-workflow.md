# Workflow: strategy, Cursor economy, schedule (read once; not needed in task chats)

## A. Strategy: vertical slices, not "framework first"
1. Thinnest foundation (P0-P1), then prove it with one end-to-end slice (task-service create -> get).
2. Grow the framework only when a test needs it (extract on the second use). Breadth per layer after the slice is green.
3. CI goes green (P5) with what exists, then only grows.
4. Order = risk first: infra hazards (xdist, template DB, app loading) are solved before writing 100 tests.

## B. Working with Cursor (token economy)
- Do NOT feed the whole lab. One-time recon (P0) makes a ~150-400-line SUT_MAP.md (routes, DI seams, env vars, quirks). Every later task reads: rule (auto) + SUT_MAP.md + the one service file it touches + the docs listed in that phase's Attach line.
- Rules auto-attach by glob (python-style: *.py; testing-core: testing/**; playwright: UI dirs; testing-modify-prod: manual @). Never paste rules.
- .cursorignore: frontend/node_modules, observability/, load-tests/, chaos/, docs/incidents-playbooks/, **/*.lock, .venv, infra/**/grafana, **/__pycache__, test-results/. (Unignore frontend/src only for P7.)
- One task = one new chat, named like "P3.2 task-service component". Commit after every green task (git commit -m "P3.2 ..."): a bad chat is just git restore.
- Models: strong model in Ask/Plan mode for P1, P2, P6 design decisions (short plan, you approve, then Agent); cheaper/auto model in Agent mode for mechanical test writing (P3, P4, P7). Task fails twice -> stop, git restore, restate narrower; drop a chat after ~15 turns or 2 failed fixes.
- Pattern once, then reuse: finish task-service, review it yourself, then "replicate @tests/component/task_service for auth-service". After the golden example P3.2-P3.6 are independent (parallel agents/worktrees if available).
- Review what matters: conftest/fixtures/flows/ports. Skim generated tests; run them 3x in random order.
- Free quality gate: make t-check (ruff + pyright + quick pytest) + pre-commit hook running the same; Cursor runs it as part of DoD.
- Mutation spot-check per service: break one prod line or flip one assertion; a test must go red (catches tautological AI tests).
- Cheap loops: terminal tails (| tail -40), -x -q, --lf.
- Interview angle: KNOWN_ISSUES.md (defects found), ADR table, README diagrams are the portfolio.

## D. Schedule
Part 1 - foundation, component, contract, CI v1: P0 -> P5.
Part 2 - integration, UI, smoke + synthetic, CI v2, polish: P6 -> P10.
Cut-line if behind (drop in this order): P10 polish -> nightly/chaos scenarios -> notification/scheduler component tests -> cross-browser -> API-coverage meta-test -> Schemathesis stateful -> sharding. (Within P8 cut P8.3 Grafana SM first.)
