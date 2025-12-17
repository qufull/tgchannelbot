from aiogram import Router, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    InputMediaPhoto, InputMediaVideo, InputMediaDocument,
)
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.keyboards.inline import admin_menu_kb
from src.models.channel import Channel
from src.models.media_item import MediaItem
from src.models.post import Post
from src.states.admin_states import AdminStates
from src.utils.config import settings
from src.utils.utils import extract_forwarded_channel_id, make_caption_and_rest, TELEGRAM_CAPTION_LIMIT, \
    TELEGRAM_TEXT_LIMIT, split_text

router = Router()


@router.message(Command("start"))
async def start(m: Message):
    await m.answer("Я готов. Команды: /admin")


@router.message(Command("admin"))
async def admin(m: Message):
    await m.answer("Админка:", reply_markup=admin_menu_kb())

@router.message(StateFilter(AdminStates.wait_target_forward))
async def set_target_from_forward(m: Message, state: FSMContext, db: AsyncSession):
    chat_id, title = extract_forwarded_channel_id(m)
    if not chat_id:
        await m.answer("Не вижу канал в пересланном. Перешли именно пост из канала.")
        return

    await db.execute(delete(Channel).where(Channel.role == "target"))
    db.add(Channel(chat_id=chat_id, role="target", title=title or "", is_active=True))
    await db.commit()

    await state.clear()
    await m.answer(f"🎯 Target подключен: {chat_id} {title}", reply_markup=admin_menu_kb())


