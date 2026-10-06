"""Self-tests for Polyfactory `.build()`. No database and no Docker."""

from saas_shared.models import TaskStatus

from saas_testkit.context import RunContext, using_context
from saas_testkit.domain import TaskCreate
from saas_testkit.factories import TaskCreateFactory, TaskRowFactory, UserRowFactory

_USERNAME_MAX = 64


def test_task_create_build_with_context_embeds_run_and_test() -> None:
    ctx = RunContext.create(run_id="run1", test_id="test1")

    with using_context(ctx):
        body = TaskCreateFactory.build()

    assert isinstance(body, TaskCreate)
    assert body.title.startswith("task-run1-test1-")


def test_task_row_build_with_context_uses_created_status() -> None:
    ctx = RunContext.create(run_id="run", test_id="row")

    with using_context(ctx):
        row = TaskRowFactory.build()

    assert row.status is TaskStatus.created


def test_task_row_factory_leaves_relationships_unset() -> None:
    assert TaskRowFactory.__set_relationships__ is False


def test_user_row_build_reuses_hashed_password() -> None:
    first = UserRowFactory.build()
    second = UserRowFactory.build()

    assert first.hashed_password == second.hashed_password
    assert first.hashed_password.startswith("$argon2")


def test_user_row_build_keeps_username_within_column_limit() -> None:
    row = UserRowFactory.build()

    assert len(row.username) <= _USERNAME_MAX
