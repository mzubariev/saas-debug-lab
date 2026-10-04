# Cursor pack: what to attach when
Placement: rules/*.mdc -> .cursor/rules/ ; docs/*.md and plan/*.md -> testing/docs/cursor/. Human docs stay in testing/docs/.
Per task chat: paste plan/01-prompt-template.md, then the phase file (plan/pN-*.md) and the docs from its Attach line. Rules attach by glob (never paste).

Design docs (design/ folder):
- arch-adr.md: goals, terms, ADR 1-18
- arch-layers-layout.md: pyramid, layer matrix, repo layout, SUT cheat sheet
- arch-core-infra.md: root conftest, template DB, worker DB, Redis, Postgres tuning, component app, helpers
- arch-adapters-factories.md: adapters, flows, Polyfactory
- arch-integration.md: compose test stack, seed/login, WireMock, integration scenarios S1-S5
- arch-ci.md: CI design, ci.yml skeleton (ci-gate), Playwright in CI, scaling
- arch-quality.md: security, flake policy, risks + fallbacks (time-boxes), anti-patterns
- cat-component.md, cat-contract.md, cat-ui.md, cat-smoke-synthetic.md: test catalogues per layer

Task -> files (plan/ folder):
- P0 recon: lab docs only (no pack docs)
- P0.1: SUT_MAP + testing-modify-prod.mdc (@)
- P0.2: arch-adr, arch-layers-layout
- P1: arch-adr, arch-core-infra, arch-adapters-factories, SUT_MAP
- P2: arch-adapters-factories, SUT_MAP
- P3.x: cat-component (service line), SUT_MAP, service files
- P4: cat-contract, SUT_MAP, arch-quality (Schemathesis row)
- P5: arch-ci (§9, §9.2)
- P6: arch-integration, SUT_MAP
- P7: cat-ui, SUT_MAP, frontend/src
- P8: cat-smoke-synthetic
- P9: arch-ci
- P10, E, F: plan/p10-polish-after.md
- Design question mid-task: the one relevant arch-*.md, not all.

Where rules live: testing-core.mdc = invariants that apply to every file in testing/** (scope, layer dirs, test bodies, data/isolation, fixtures, quality gates, time-box). Docs = rationale, skeletons, catalogues, CI. A fact is stored in one place; docs point to the rule instead of repeating it.
