"""Task board. Drag and drop uses pointer moves because dnd-kit ignores `drag_to`."""

from playwright.sync_api import Locator, Page, expect

from saas_testkit.adapters.playwright.components.kanban import KanbanColumn, TaskCard
from saas_testkit.domain.tasks import TaskStatus

_DRAG_STEPS = 25


class BoardPage:
    def __init__(self, page: Page) -> None:
        self._page = page
        self._heading = page.get_by_role("heading", name="Task Board", exact=True)
        self._new = page.get_by_role("button", name="+ New Task", exact=True)
        self._title = page.get_by_label("Title")
        self._create = page.get_by_role("button", name="Create task", exact=True)
        self._columns = {status: KanbanColumn(page, status) for status in TaskStatus}

    def open(self) -> None:
        self._page.goto("/")

    def reload(self) -> None:
        self._page.reload()
        self._ready()

    def create_task(self, title: str) -> None:
        self._ready()
        self._new.click()
        self._title.fill(title)
        self._create.click()

    def move_task(self, task: str, *, to: TaskStatus) -> None:
        self._ready()
        card = self._require(task)
        card.expect_visible()
        self._drag(card.root, self._columns[to].root)

    def expect_open(self) -> None:
        self._ready()

    def expect_task(self, task: str, *, column: TaskStatus) -> None:
        self._ready()
        found = self._columns[column].reveal(task)
        if found is None:
            raise AssertionError(f"task {task} is not in {column.value}")
        found.expect_visible()

    def task_id(self, task: str) -> str:
        return self._require(task).task_id()

    def _ready(self) -> None:
        expect(self._heading).to_be_visible()
        expect(self._columns[TaskStatus.created].root).to_be_visible()

    def _require(self, title: str) -> TaskCard:
        for column in self._columns.values():
            found = column.reveal(title)
            if found is not None:
                return found
        raise AssertionError(f"task {title} is not on the board")

    def _drag(self, source: Locator, target: Locator) -> None:
        """Move the pointer in steps so dnd-kit's 5px activation distance is crossed."""
        source.scroll_into_view_if_needed()
        target.scroll_into_view_if_needed()
        start = _center(source)
        end = _center(target)
        mouse = self._page.mouse
        mouse.move(start[0], start[1])
        mouse.down()
        mouse.move(end[0], end[1], steps=_DRAG_STEPS)
        mouse.up()


def _center(locator: Locator) -> tuple[float, float]:
    box = locator.bounding_box()
    if box is None:
        raise RuntimeError("drag handle has no box")
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
