"""
src/handlers/admin/sources.py
Управление источниками (каналами для мониторинга)
"""

import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.keyboards.admin_channels import sources_menu_kb, sources_list_kb, source_actions_kb
from src.keyboards.inline import admin_menu_kb
from src.models.channel import Channel
from src.states.admin_states import AdminStates
from src.userbot.client import userbot

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "src:list")
async def list_sources(c: CallbackQuery, db: AsyncSession):
    """Список источников"""
    result = await db.execute(
        select(Channel).where(Channel.role == "source")
    )
    sources = result.scalars().all()

    if not sources:
        await c.message.edit_text(
            "📡 <b>Источники</b>\n\n"
            "Список пуст. Добавьте канал для мониторинга.",
            reply_markup=sources_menu_kb(),
            parse_mode="HTML"
        )
    else:
        await c.message.edit_text(
            "📡 <b>Источники</b>\n\n"
            "Выберите канал для управления:",
            reply_markup=sources_list_kb(sources),
            parse_mode="HTML"
        )
    await c.answer()


@router.callback_query(F.data == "src:add")
async def add_source_start(c: CallbackQuery, state: FSMContext):
    """Начало добавления источника"""
    await state.set_state(AdminStates.wait_source_link)
    await c.message.edit_text(
        "📡 <b>Добавление источника</b>\n\n"
        "Отправьте ссылку на канал:\n\n"
        "• <code>@channel</code> — публичный канал\n"
        "• <code>t.me/channel</code> — публичный канал\n"
        "• <code>t.me/+ABC123</code> — приватный канал\n"
        "• <code>t.me/joinchat/ABC123</code> — приватный канал\n\n"
        "Юзербот автоматически подпишется на канал.",
        parse_mode="HTML"
    )
    await c.answer()


@router.message(AdminStates.wait_source_link)
async def add_source_process(m: Message, state: FSMContext, db: AsyncSession):
    """Обработка ссылки на источник"""
    link = m.text.strip()

    if not link:
        await m.answer("❌ Отправьте ссылку на канал")
        return

    await m.answer("⏳ Подключаюсь к каналу...")

    # Всегда вызываем join_channel — он сам разберётся приватный или публичный
    info = await userbot.join_channel(link)

    if not info:
        await m.answer(
            "❌ Не удалось подключиться к каналу.\n\n"
            "Проверьте:\n"
            "• Ссылка корректная\n"
            "• Ссылка не истекла\n"
            "• Канал существует",
            reply_markup=sources_menu_kb()
        )
        await state.clear()
        return

    # Проверяем, не добавлен ли уже
    existing = await db.execute(
        select(Channel).where(
            Channel.chat_id == info["chat_id"],
            Channel.role == "source"
        )
    )
    if existing.scalars().first():
        await m.answer(
            f"⚠️ Канал <b>{info['title']}</b> уже добавлен как источник.",
            reply_markup=sources_menu_kb(),
            parse_mode="HTML"
        )
        await state.clear()
        return

    # Добавляем в БД
    channel = Channel(
        chat_id=info["chat_id"],
        title=info["title"],
        role="source",
        is_active=True
    )
    db.add(channel)
    await db.commit()

    # Сбрасываем кеш
    userbot.invalidate_cache()

    await m.answer(
        f"✅ Источник добавлен!\n\n"
        f"<b>{info['title']}</b>\n"
        f"<code>{info['chat_id']}</code>",
        reply_markup=sources_menu_kb(),
        parse_mode="HTML"
    )
    await state.clear()


@router.callback_query(F.data.startswith("src:view:"))
async def view_source(c: CallbackQuery, db: AsyncSession):
    """Просмотр источника"""
    channel_id = int(c.data.split(":")[2])

    channel = await db.get(Channel, channel_id)
    if not channel:
        await c.answer("Канал не найден", show_alert=True)
        return

    status = "✅ Активен" if channel.is_active else "⏸ Приостановлен"

    await c.message.edit_text(
        f"📡 <b>{channel.title}</b>\n\n"
        f"ID: <code>{channel.chat_id}</code>\n"
        f"Статус: {status}",
        reply_markup=source_actions_kb(channel.id, channel.is_active),
        parse_mode="HTML"
    )
    await c.answer()


@router.callback_query(F.data.startswith("src:toggle:"))
async def toggle_source(c: CallbackQuery, db: AsyncSession):
    """Вкл/выкл источник"""
    channel_id = int(c.data.split(":")[2])

    channel = await db.get(Channel, channel_id)
    if not channel:
        await c.answer("Канал не найден", show_alert=True)
        return

    channel.is_active = not channel.is_active
    await db.commit()

    userbot.invalidate_cache()

    status = "✅ Активен" if channel.is_active else "⏸ Приостановлен"
    await c.message.edit_text(
        f"📡 <b>{channel.title}</b>\n\n"
        f"ID: <code>{channel.chat_id}</code>\n"
        f"Статус: {status}",
        reply_markup=source_actions_kb(channel.id, channel.is_active),
        parse_mode="HTML"
    )
    await c.answer("Статус изменён")


@router.callback_query(F.data.startswith("src:delete:"))
async def delete_source(c: CallbackQuery, db: AsyncSession):
    """Удалить источник"""
    channel_id = int(c.data.split(":")[2])

    channel = await db.get(Channel, channel_id)
    if channel:
        await db.delete(channel)
        await db.commit()
        userbot.invalidate_cache()

    await c.message.edit_text(
        "🗑 Источник удалён",
        reply_markup=sources_menu_kb()
    )
    await c.answer()


@router.callback_query(F.data == "src:back")
async def back_to_sources(c: CallbackQuery):
    """Назад к меню источников"""
    await c.message.edit_text(
        "📡 <b>Источники для мониторинга</b>\n\n"
        "Юзербот следит за этими каналами.",
        reply_markup=sources_menu_kb(),
        parse_mode="HTML"
    )
    await c.answer()


@router.callback_query(F.data == "src:main")
async def back_to_main(c: CallbackQuery):
    """Назад в главное меню"""
    await c.message.edit_text(
        "⚙️ <b>Админка</b>",
        reply_markup=admin_menu_kb(),
        parse_mode="HTML"
    )
    await c.answer()