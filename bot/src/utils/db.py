from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from src.utils.config import settings

engine = create_async_engine(
	url=settings.DATABASE_URL_asyncpg,
)

session = async_sessionmaker(engine,  expire_on_commit=False)

async def create_tables() -> None:
    if engine is None:
        raise RuntimeError("DB engine is not initialized.")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db():
    if engine is None:
        raise RuntimeError("DB engine is not initialized.")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

async def close_db() -> None:
    await engine.dispose()

class Base(DeclarativeBase):
	pass