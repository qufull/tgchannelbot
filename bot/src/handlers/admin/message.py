from aiogram import Router, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
)
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.keyboards.inline import admin_menu_kb, start_kb
from src.models.channel import Channel
from src.states.admin_states import AdminStates
from src.utils.utils import extract_forwarded_channel_id


router = Router()


@router.message(Command("start"))
async def start(m: Message):
    await m.answer("Я готов. Команды: /admin", reply_markup=start_kb())


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


