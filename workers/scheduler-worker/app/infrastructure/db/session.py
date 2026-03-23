from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

_engine: Engine | None = None


def get_sync_engine(dsn: str) -> Engine:
    """Lazy singleton sync engine — avoids DB connections at Celery import time."""
    global _engine
    if _engine is None:
        _engine = create_engine(dsn, pool_pre_ping=True)
    return _engine
