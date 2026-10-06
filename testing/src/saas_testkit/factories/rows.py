"""ORM rows. `.build()` does no I/O. `create_async()` commits through the bound session."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from argon2 import PasswordHasher
from polyfactory import Use
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from saas_shared.models import Task as TaskRow
from saas_shared.models import TaskStatus
from saas_shared.models import User as UserRow

from saas_testkit.context import unique_title

# One hash for the whole process. Argon2 is too slow to repeat per row.
_PASSWORD_HASH = PasswordHasher().hash("user123")


class TaskRowFactory(SQLAlchemyFactory[TaskRow]):
    __model__ = TaskRow
    __set_relationships__ = False

    title = Use(unique_title, "task")
    status = TaskStatus.created
    created_at = Use(lambda: datetime.now(UTC))
    updated_at = Use(lambda: datetime.now(UTC))


class UserRowFactory(SQLAlchemyFactory[UserRow]):
    __model__ = UserRow
    __set_relationships__ = False

    # `users.username` is varchar(64). A full node id does not fit.
    username = Use(lambda: f"user-{uuid4().hex[:16]}")
    hashed_password = _PASSWORD_HASH
    role = "user"


@dataclass(frozen=True, slots=True, kw_only=True)
class Rows:
    task: type[TaskRowFactory]
    user: type[UserRowFactory]
