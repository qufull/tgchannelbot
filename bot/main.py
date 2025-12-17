import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from src.handlers import router
from src.userbot.client import userbot
from src.utils.config import settings
from src.utils.middlewares import DataBaseMiddleware, AdminOnlyMiddleware
from src.utils.db import session as db_session, create_tables, close_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def start_userbot():
    """Запуск юзербота"""
    try:
        await userbot.start()
        logger.info("Userbot running...")
        await userbot.run_until_disconnected()
    except Exception as e:
        logger.exception(f"Userbot error: {e}")

async def main():

    await create_tables()

    session = AiohttpSession()
    bot = Bot(
        token=settings.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
              )

    userbot.set_bot(bot)

    dp = Dispatcher(storage=MemoryStorage())

    dp.update.middleware(DataBaseMiddleware(db_session))
    dp.update.middleware(AdminOnlyMiddleware())
    dp.include_router(router)

    userbot_task = asyncio.create_task(start_userbot())

    try:
        await dp.start_polling(bot)
    except ValueError as e:
        logger.error(e)
    except KeyError as e:
        logger.error(e)
    finally:
        await bot.session.close()
        await userbot.stop()
        await close_db()

if __name__ == '__main__':
    asyncio.run(main())