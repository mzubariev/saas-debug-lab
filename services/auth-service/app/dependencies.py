from .infrastructure.db.session import SessionLocal


async def get_db():
    async with SessionLocal() as session:
        yield session
