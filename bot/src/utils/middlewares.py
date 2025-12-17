
import logging
from typing import Any, Awaitable, Callable, Dict, Union

from aiogram import BaseMiddleware
from aiogram.types import Update, Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.utils.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class DataBaseMiddleware(BaseMiddleware):  # pylint: disable=too-few-public-methods
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]):
        super().__init__()
        self.sessionmaker = sessionmaker

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        async with self.sessionmaker() as db:
            data["db"] = db
            try:
                result = await handler(event, data)
                await db.commit()
                return result
            except Exception:
                await db.rollback()
                raise

class AdminOnlyMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        obj = getattr(event, "message", None) or getattr(event, "callback_query", None)
        if obj is None:
            return await handler(event, data)

        user = obj.from_user
        if not user or user.id not in settings.ADMIN_IDS:
            # отвечаем аккуратно
            if isinstance(obj, Message):
                await obj.answer(f"Нет доступа. Твой id: {getattr(user, 'id', 'unknown')}")
            elif isinstance(obj, CallbackQuery):
                await obj.answer("Нет доступа", show_alert=True)
            return None

        return await handler(event, data)

