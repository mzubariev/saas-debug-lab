# Test catalogue: e2e_ui (P7)
Rules: playwright.mdc. Characterise first; record surprises in KNOWN_ISSUES.md.
Principle: UI tests prove that the browser, the frontend and the gateway work together. Business rules are already covered below this layer, so keep the set small: about 6 tests.
Tiers: T1 = must, T2 = if time, T3 = not planned.

T1:
- login success (no storage_state) `@critical`
- login failure shows an error (no storage_state)
- unauthenticated visit to the board redirects to login
- full task lifecycle: create task via UI: the card appears in the first column, drag to In Progress persists after reload, drag to Completed persists after reload (verified via API) `@critical`

Fast PR subset (`@pytest.mark.critical`) = login success + create + move.
Run: -n 2, nginx :80 for UI, data created via API, login once per run (storage_state).
