# P7 - Playwright UI
Attach: cat-ui.md, SUT_MAP.md, frontend/src (pages + components only).
1. Prod frontend code (if needed for Playwright POM): accessible names / data-testid on login form, board columns, task cards (testing-modify-prod.mdc).
2. Prompt: Pages: LoginPage, BoardPage; components: KanbanColumn, TaskCard (locators in __init__, prefer roles/labels; if the frontend has no accessible names/test ids, list the missing ones in KNOWN_ISSUES.md and use the most stable CSS). tests/e2e_ui/conftest.py: browser_context_args (service_workers=block, storage_state from the per-run token file), API data fixtures, flows in business language. Drag-and-drop (dnd-kit) through one helper using mouse.move(..., steps=N), not drag_to. Tests per catalogue; @pytest.mark.critical on login+create+move.
DoD: `make t-ui` green headless; failure produces trace + screenshot; -n 2 stable 3x.
