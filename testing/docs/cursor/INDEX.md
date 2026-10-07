# Cursor pack: what to attach and when

Layout in the repository:
- `.cursor/rules/*.mdc`: the four rules (from `rules/`).
- `testing/docs/cursor/`: this file, `design/`, `plan/`, `KIT_MAP.md`, and `sut/` (`SUT_MAP.md` for common facts, one file per service, plus `_prep.md` for P0.1 and `_recon-log.md` as evidence).
- `testing/docs/human/`: the human documents `TESTING_ARCHITECTURE.md` and `IMPLEMENTATION_PLAN.md`.

This pack is the source of truth for agents. The two human documents were synchronised with it once, at the revision of October 2026. After that, edit the pack first and update the human documents only when you want them current; do not maintain both by hand in parallel.

## How to run a task
1. Open a new chat named after the phase.
2. Paste `plan/01-prompt-template.md` and fill it in from the phase file.
3. Attach the files named in the phase file's `Attach:` line, plus `sut/SUT_MAP.md`, the `sut/<service>.md` of each service the task touches, and (from P3 on) `KIT_MAP.md`. Rules attach by glob, and `@testing-core.mdc` is already in the template.

## Design documents (`design/`)
- `arch-adr.md`: goals, terms and ADR 1 to 18.
- `arch-layers-layout.md`: pyramid, layer matrix, repository layout and the provisional SUT cheat sheet.
- `arch-core-infra.md`: root conftest, template database, worker database, Redis, Postgres tuning, the component app and helpers.
- `arch-adapters-factories.md`: adapters, flows and Polyfactory.
- `arch-integration.md`: the compose test stack, seed and login, WireMock and integration scenarios S1 to S5.
- `arch-ci.md`: CI design, the `ci.yml` skeleton with `ci-gate`, Playwright in CI and the scaling model.
- `arch-quality.md`: security testing, flake policy, risks with fallbacks and time-boxes, and anti-patterns.
- `cat-component.md`, `cat-contract.md`, `cat-ui.md`, `cat-smoke-synthetic.md`: test catalogues per layer.

## Task to files
- P0 recon: the lab's own docs only (README, ARCHITECTURE, FILE_STRUCTURE, SERVICE_MAP). No pack documents.
- P0.1: `sut/SUT_MAP.md` and `testing-modify-prod.mdc` (with `@`).
- P0.2: `arch-adr`, `arch-layers-layout`.
- P1: `arch-adr`, `arch-core-infra`, `arch-adapters-factories`, `sut/SUT_MAP.md`.
- P2: `arch-adapters-factories`, `sut/SUT_MAP.md`.
- P3.x: `cat-component` (the service's line), `sut/SUT_MAP.md`, KIT_MAP and the service files.
- P4: `cat-contract`, `sut/SUT_MAP.md`, KIT_MAP and the Schemathesis row of `arch-quality` section 11.
- P5: `arch-ci` (sections 9 and 9.2).
- P6.0 (KRaft, separate branch): the lab's compose files only; no pack documents.
- P6.1 to P6.3: `arch-integration`, `sut/SUT_MAP.md`, KIT_MAP.
- P7: `cat-ui`, `sut/SUT_MAP.md`, KIT_MAP and `frontend/src`.
- P8: `cat-smoke-synthetic`, KIT_MAP.
- P9: `arch-ci` (all), KIT_MAP.
- P10, E, F: `plan/p10-polish-after.md`.
- A design question in the middle of a task: attach the one relevant design document, not all of them.

## Where a fact lives
`testing-core.mdc` holds policy that applies to every file in `testing/**`. `sut/SUT_MAP.md` holds facts about the system under test. `KIT_MAP.md` holds what the testkit offers. The design documents hold rationale, skeletons, catalogues and CI. Each fact lives in one place, and documents point to the rule instead of repeating it.
