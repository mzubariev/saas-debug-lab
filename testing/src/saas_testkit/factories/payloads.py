"""Request bodies. `.build()` does no I/O."""

from polyfactory import Use
from polyfactory.factories.pydantic_factory import ModelFactory

from saas_testkit.context import unique_title
from saas_testkit.domain.tasks import TaskCreate


class TaskCreateFactory(ModelFactory[TaskCreate]):
    __model__ = TaskCreate

    title = Use(unique_title, "task")
