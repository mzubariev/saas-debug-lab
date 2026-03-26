"""Tasks table — ORM definition lives in `saas_shared.models` (shared with Alembic)."""

from saas_shared.models import Task, TaskStatus
from saas_shared.models.base import Base

__all__ = ["Task", "TaskStatus", "Base"]
