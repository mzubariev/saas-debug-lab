"""Create a task in the browser and drag it across the board."""

import pytest

from saas_testkit.context import unique_title
from saas_testkit.domain import TaskStatus


@pytest.mark.critical
def test_created_task_stays_in_each_column_after_reload(board, tasks) -> None:
    title = unique_title("task")
    board.open()
    board.create_task(title)
    board.expect_task(title, column=TaskStatus.created)

    board.move_task(title, to=TaskStatus.in_progress)
    board.reload()
    board.expect_task(title, column=TaskStatus.in_progress)
    started = tasks.find(title)
    assert started is not None
    assert started.status is TaskStatus.in_progress

    board.move_task(title, to=TaskStatus.completed)
    board.reload()
    board.expect_task(title, column=TaskStatus.completed)
    finished = tasks.find(title)
    assert finished is not None
    assert finished.status is TaskStatus.completed
