__all__ = ("router",)

from aiogram import Router

from src.handlers.ai.handler import router as ai_router


router = Router()

router.include_routers(ai_router)