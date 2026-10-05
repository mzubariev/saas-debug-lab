# P7: Playwright UI tests
Attach: `design/cat-ui.md`, `SUT_MAP.md`, `sut/api-gateway.md`, `KIT_MAP.md` and `frontend/src` (pages and components only). Un-ignore `frontend/src` first.

Must do:
1. If Playwright page objects need it, add accessible names or `data-testid` to the login form, the board columns and the task cards, following `testing-modify-prod.mdc`.
2. Run this prompt: create the pages `LoginPage` and `BoardPage` and the components `KanbanColumn` and `TaskCard`, with locators in `__init__` (prefer roles and labels; if the frontend has no accessible names or test ids, list the missing ones in `KNOWN_ISSUES.md` and use the most stable CSS). Create `tests/e2e_ui/conftest.py` with `browser_context_args` (`service_workers=block`, `storage_state` from the per-run token file), API data fixtures and business-language flows. Implement drag and drop (dnd-kit) in one helper using `mouse.move(..., steps=N)`, not `drag_to`. Write the tests from the catalogue, and mark login, create and move with `@pytest.mark.critical`.

Definition of done: `make t-ui` is green headless, a failure produces a trace and a screenshot, `-n 2` is stable three times, and `KIT_MAP.md` lists the page objects.
