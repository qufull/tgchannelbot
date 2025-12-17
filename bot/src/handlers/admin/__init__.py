__all__ = ("router",)

from aiogram import Router

from src.handlers.admin.message import router as message_router
from src.handlers.admin.callback import router as callback_router

router = Router()

router.include_routers(message_router,callback_router)
