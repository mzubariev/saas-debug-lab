"""Board widgets. Columns and cards have no accessible name, so these use their class."""

import re

from playwright.sync_api import Locator, Page, expect

from saas_testkit.domain.tasks import TaskStatus

_LABELS = {
    TaskStatus.created: "Created",
    TaskStatus.in_progress: "In Progress",
    TaskStatus.completed: "Completed",
}


class TaskCard:
    def __init__(self, root: Locator) -> None:
        self._root = root
        self._title = root.locator(".task-card__title")
        self._id = root.locator(".task-card__id")

    @property
    def root(self) -> Locator:
        return self._root

    def expect_visible(self) -> None:
        expect(self._root).to_be_visible()

    def task_id(self) -> str:
        self.expect_visible()
        value = self._id.get_attribute("title")
        if not value:
            raise RuntimeError("task card has no id")
        return value


class KanbanColumn:
    def __init__(self, page: Page, status: TaskStatus) -> None:
        label = _LABELS[status]
        self._root = page.locator(".column").filter(
            has=page.locator(".column__title", has_text=re.compile(rf"^{re.escape(label)}$"))
        )
        self._cards = self._root.locator(".task-card")
        self._next = self._root.get_by_role("button", name="→", exact=True)
        self._prev = self._root.get_by_role("button", name="←", exact=True)
        self._page_label = self._root.locator(".column__pagination span")

    @property
    def root(self) -> Locator:
        return self._root

    def card(self, title: str) -> TaskCard:
        exact = re.compile(rf"^{re.escape(title)}$")
        title_node = self._root.locator(".task-card__title", has_text=exact)
        return TaskCard(self._cards.filter(has=title_node))

    def reveal(self, title: str) -> TaskCard | None:
        """The column shows 10 cards per page. Walk pages until this title is mounted."""
        self._to_first_page()
        for _ in range(50):
            found = self.card(title)
            if found.root.count() > 0:
                return found
            if self._next.count() == 0 or not self._next.is_enabled():
                return None
            label = self._page_label.inner_text()
            self._next.click()
            expect(self._page_label).not_to_have_text(label)
        return None

    def _to_first_page(self) -> None:
        for _ in range(50):
            if self._prev.count() == 0 or not self._prev.is_enabled():
                return
            label = self._page_label.inner_text()
            self._prev.click()
            expect(self._page_label).not_to_have_text(label)
