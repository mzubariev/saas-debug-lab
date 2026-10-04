# Test catalogue: e2e_ui (P7)
Rules: playwright.mdc. Characterise first; record surprises in KNOWN_ISSUES.md.
- login success/failure (no storage_state)
- unauthenticated redirect
- board shows own task
- create task via UI (card in first column)
- drag to In Progress persists after reload (verified via API)
- drag to Completed
- fast PR subset (@pytest.mark.critical) = login + create + move
Run: -n 2, nginx :80 for UI, data created via API, login once per run (storage_state).
