from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.keyboards.admin_channels import sources_menu_kb, cancel_kb, sources_list_kb, source_detail_kb, \
    confirm_delete_kb
from src.models.channel import Channel
from src.states.admin_channel import SourceStates
from src.userbot.client import userbot

router = Router()

@router.callback_query(F.data == "adm:sources")
async def open_sources_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.edit_text(
        "📡 <b>Источники для мониторинга</b>\n\n"
        "Юзербот следит за этими каналами и форвардит новые посты в инбокс.",
        reply_markup=sources_menu_kb(),
        parse_mode="HTML"
    )
    await c.answer()


@router.callback_query(F.data == "src:menu")
async def sources_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.edit_text(
        "📡 <b>Источники для мониторинга</b>\n\n"
        "Юзербот следит за этими каналами и форвардит новые посты в инбокс.",
        reply_markup=sources_menu_kb(),
        parse_mode="HTML"
    )
    await c.answer()


@router.callback_query(F.data == "src:back_admin")
async def back_to_admin(c: CallbackQuery, state: FSMContext):
    from src.keyboards.inline import admin_menu_kb
    await state.clear()
    await c.message.edit_text("Админка:", reply_markup=admin_menu_kb())
    await c.answer()


# ─────────────────────────────────────────────────────────────
# Список источников
# ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "src:list")
async def list_sources(c: CallbackQuery, db: AsyncSession):
    result = await db.execute(
        select(Channel).where(Channel.role == "source").order_by(Channel.id.desc())
    )
    sources = result.scalars().all()

    if not sources:
        await c.message.edit_text(
            "📋 <b>Источники</b>\n\n"
            "Список пуст. Добавьте каналы для мониторинга.",
            reply_markup=sources_menu_kb(),
            parse_mode="HTML"
        )
    else:
        active = sum(1 for s in sources if s.is_active)
        await c.message.edit_text(
            f"📋 <b>Источники</b>\n\n"
            f"Всего: {len(sources)} (активных: {active})",
            reply_markup=sources_list_kb(sources),
            parse_mode="HTML"
        )
    await c.answer()


@router.callback_query(F.data.startswith("src:page:"))
async def sources_page(c: CallbackQuery, db: AsyncSession):
    page = int(c.data.split(":")[2])
    result = await db.execute(
        select(Channel).where(Channel.role == "source").order_by(Channel.id.desc())
    )
    sources = result.scalars().all()
    await c.message.edit_reply_markup(reply_markup=sources_list_kb(sources, page))
    await c.answer()


# ─────────────────────────────────────────────────────────────
# Добавление источника
# ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "src:add")
async def add_source_start(c: CallbackQuery, state: FSMContext):
    await state.set_state(SourceStates.wait_channel)
    await c.message.edit_text(
        "➕ <b>Добавление источника</b>\n\n"
        "Отправьте ссылку или @username канала:\n\n"
        "• <code>@channel</code>\n"
        "• <code>https://t.me/channel</code>\n"
        "• <code>https://t.me/c/1234567890/1</code>\n\n"
        "⚠️ Юзербот должен быть подписан на канал!",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await c.answer()


@router.message(SourceStates.wait_channel)
async def add_source_process(m: Message, state: FSMContext, db: AsyncSession):
    text = m.text.strip()

    # Пробуем получить инфо через юзербот
    info = await userbot.get_channel_info(text)

    if info:
        chat_id = info["chat_id"]
        title = info["title"]
    else:
        # Парсим вручную для приватных каналов
        chat_id = None
        title = ""

        if "t.me/c/" in text:
            try:
                parts = text.split("/c/")[1].split("/")
                chat_id = -int("100" + parts[0])
            except:
                await m.answer("❌ Неверный формат. Попробуйте ещё раз:")
                return
        else:
            await m.answer(
                "❌ Не удалось найти канал.\n\n"
                "Убедитесь, что юзербот подписан на этот канал.",
                reply_markup=sources_menu_kb()
            )
            await state.clear()
            return

    # Проверка на дубликат
    exists = await db.execute(
        select(Channel).where(Channel.chat_id == chat_id)
    )
    existing = exists.scalar()

    if existing:
        if existing.role == "source":
            await m.answer("⚠️ Этот канал уже добавлен как источник!", reply_markup=sources_menu_kb())
        else:
            await m.answer(
                f"⚠️ Этот канал уже используется как {existing.role}!",
                reply_markup=sources_menu_kb()
            )
        await state.clear()
        return

    # Добавляем как source
    source = Channel(
        chat_id=chat_id,
        role="source",
        title=title or "",
        is_active=True
    )
    db.add(source)
    await db.commit()

    # Сбрасываем кеш юзербота
    userbot.invalidate_cache()

    await state.clear()
    await m.answer(
        f"✅ <b>Источник добавлен!</b>\n\n"
        f"Канал: {title or chat_id}\n"
        f"ID: <code>{chat_id}</code>\n\n"
        f"Новые посты будут форвардиться в инбокс.",
        reply_markup=sources_menu_kb(),
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────────────────────
# Детали источника
# ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("src:view:"))
async def view_source(c: CallbackQuery, db: AsyncSession):
    source_id = int(c.data.split(":")[2])
    source = await db.get(Channel, source_id)

    if not source or source.role != "source":
        await c.answer("Не найден", show_alert=True)
        return

    status = "✅ Активен" if source.is_active else "❌ Отключён"
    name = source.title or str(source.chat_id)

    await c.message.edit_text(
        f"📢 <b>{name}</b>\n\n"
        f"ID: <code>{source.chat_id}</code>\n"
        f"Статус: {status}",
        reply_markup=source_detail_kb(source_id, source.is_active),
        parse_mode="HTML"
    )
    await c.answer()


# ─────────────────────────────────────────────────────────────
# Управление источником
# ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("src:toggle:"))
async def toggle_source(c: CallbackQuery, db: AsyncSession):
    source_id = int(c.data.split(":")[2])
    source = await db.get(Channel, source_id)

    if not source or source.role != "source":
        await c.answer("Не найден", show_alert=True)
        return

    source.is_active = not source.is_active
    await db.commit()

    # Сбрасываем кеш
    userbot.invalidate_cache()

    status = "включён ✅" if source.is_active else "отключён ❌"
    await c.answer(f"Мониторинг {status}", show_alert=True)

    name = source.title or str(source.chat_id)
    status_text = "✅ Активен" if source.is_active else "❌ Отключён"

    await c.message.edit_text(
        f"📢 <b>{name}</b>\n\n"
        f"ID: <code>{source.chat_id}</code>\n"
        f"Статус: {status_text}",
        reply_markup=source_detail_kb(source_id, source.is_active),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("src:del:"))
async def delete_source_confirm(c: CallbackQuery, db: AsyncSession):
    source_id = int(c.data.split(":")[2])
    source = await db.get(Channel, source_id)

    if not source or source.role != "source":
        await c.answer("Не найден", show_alert=True)
        return

    name = source.title or str(source.chat_id)
    await c.message.edit_text(
        f"🗑 <b>Удалить источник?</b>\n\n{name}",
        reply_markup=confirm_delete_kb(source_id),
        parse_mode="HTML"
    )
    await c.answer()


@router.callback_query(F.data.startswith("src:del_yes:"))
async def delete_source(c: CallbackQuery, db: AsyncSession):
    source_id = int(c.data.split(":")[2])

    source = await db.get(Channel, source_id)
    if source and source.role == "source":
        await db.delete(source)
        await db.commit()

        # Сбрасываем кеш
        userbot.invalidate_cache()

    await c.answer("✅ Удалено", show_alert=True)

    # Показываем список
    result = await db.execute(
        select(Channel).where(Channel.role == "source").order_by(Channel.id.desc())
    )
    sources = result.scalars().all()

    if not sources:
        await c.message.edit_text(
            "📋 <b>Источники</b>\n\nСписок пуст.",
            reply_markup=sources_menu_kb(),
            parse_mode="HTML"
        )
    else:
        await c.message.edit_text(
            f"📋 <b>Источники</b>\n\nВсего: {len(sources)}",
            reply_markup=sources_list_kb(sources),
            parse_mode="HTML"
        )