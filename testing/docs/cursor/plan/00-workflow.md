# Workflow: strategy, working with Cursor, schedule

This file is for you, not for task chats. Read it once.

## A. Strategy: vertical slices, not "framework first"
1. Build the thinnest possible foundation (P0 and P1), then prove it with one end-to-end slice: task-service create followed by get.
2. Grow the framework only when a test needs it, and extract a helper on its second use. Add breadth per layer only after the slice is green.
3. Get CI green (P5) with what already exists, then let it only grow.
4. Work in order of risk: solve the infrastructure hazards (xdist, template database, app loading) before writing a hundred tests.

## B. Working with Cursor (token economy)
- Do not feed the whole lab to the agent. A one-time recon (P0) turns the code into a 150–400 line `testing/docs/cursor/sut/SUT_MAP.md` (routes, DI seams, environment variables, quirks). After that, every task reads the auto-attached rules, `testing/docs/cursor/sut/SUT_MAP.md`, `KIT_MAP.md`, the one service file it touches, and the design documents named in its `Attach:` line.
- Rules attach by glob: `python-style` to `*.py`, `testing-core` to `testing/**`, `playwright` to the UI directories. `testing-modify-prod` is attached manually with `@`. The prompt template also names `@testing-core.mdc` explicitly, because a glob rule attaches only after a matching file is in context. Never paste rule text into a chat.
- Keep `.cursorignore` aligned with the phase you are in. It should ignore `frontend/node_modules`, `frontend/dist`, `observability/`, `load-tests/config`, `load-tests/scripts`, `chaos/`, the incident and on-call docs, lockfiles, `.venv`, caches and `test-results/`. Un-ignore `frontend/src`, `vite.config.*`, `frontend/Dockerfile` and `frontend/package.json` before P0.1 item 5 and P7, and `load-tests/lib` before P8.3. An agent that cannot read a file tends to invent its contents, so unblock what a phase needs before you start it.
- One task is one new chat, named like "P3.1 task-service component". Commit after every green task (`git commit -m "P3.1 ..."`), so a bad chat costs only a `git restore`.
- Use a strong model in Ask or Plan mode for the design decisions of P1, P2 and P6 (the agent proposes a short plan, you approve it, then it runs in Agent mode). Use a cheaper model in Agent mode for mechanical test writing (P3, P4, P7). If a task fails twice, stop, `git restore`, restate it more narrowly and start a new chat. Drop a chat after about 15 turns or two failed fixes.
- Establish a pattern once, then reuse it. Finish task-service, review it yourself, then ask for "the same structure as `@tests/component/task_service` for auth-service". After this golden example, P3.2 to P3.6 are independent and can run in parallel agents or worktrees.
- Review what matters: `conftest.py`, fixtures, flows and ports. Skim the generated tests, and run them three times in random order.
- The free quality gate is `make t-check` (ruff, pyright and a quick pytest), which a pre-commit hook also runs. The final gate is `make t-gate` (three runs, random order, `-n auto`), run once at the end of a task, not on every fix attempt.
- Spot-check each service with a mutation: break one production line or flip one assertion, and a test must turn red. This catches tautological AI-written tests.
- Keep loops cheap: pipe terminal output through `tail -40`, and use `-x -q --lf`.
- Keep two living files current. `testing/docs/cursor/KIT_MAP.md` lists what the testkit already offers, so agents do not re-create helpers. The "Decisions since the plan" section of `testing/KNOWN_ISSUES.md` records one line per deviation from the plan, so a later chat does not undo a deliberate choice.
- Interview angle: `KNOWN_ISSUES.md` (defects found), the ADR table and the README diagrams are the portfolio.

## D. Schedule
- Part 1 covers the foundation, component and contract tests and CI v1: P0 to P5.
- Part 2 covers integration, UI, smoke and synthetic tests, CI v2 and polish: P6 to P10.
- If you fall behind, cut in this order: P10 polish, nightly and chaos scenarios, notification and scheduler component tests, cross-browser runs, the API-coverage meta-test, Schemathesis stateful mode, sharding. Within P8, cut P8.3 (Grafana) first.
