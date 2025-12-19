from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, async_session, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from src.utils.config import settings

engine = create_async_engine(
	url=settings.DATABASE_URL_asyncpg,
)

async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def session():
    """Контекстный менеджер для сессии БД"""
    async with async_session_maker() as s:
        try:
            yield s
            await s.commit()
        except Exception:
            await s.rollback()
            raise

async def create_tables() -> None:
    if engine is None:
        raise RuntimeError("DB engine is not initialized.")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def close_db() -> None:
    await engine.dispose()

class Base(DeclarativeBase):
	pass