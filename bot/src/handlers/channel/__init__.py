__all__ = ("router",)

from aiogram import Router

from src.handlers.channel.handler import router as channel_router


router = Router()

router.include_routers(channel_router)