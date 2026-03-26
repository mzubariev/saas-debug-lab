from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Single declarative base for all shared ORM models (one Alembic metadata)."""

    pass
