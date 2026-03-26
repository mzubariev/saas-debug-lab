"""Users table — ORM definition lives in `saas_shared.models` (shared with Alembic)."""

from saas_shared.models import User
from saas_shared.models.base import Base

__all__ = ["User", "Base"]
