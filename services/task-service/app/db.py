from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from .config import settings


engine = create_async_engine(
    settings.postgres_dsn,
    echo=False
)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False
)