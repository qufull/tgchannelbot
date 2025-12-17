__all__ = ("router",)

from aiogram import Router
from src.handlers.admin import router as admin_router
from src.handlers.ai import router as ai_router
from src.handlers.channel import router as channel_router
router = Router()


router.include_routers(admin_router,ai_router,channel_router)