import asyncio

from aiogram import Router, Bot, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.keyboards.admin_channels import sources_menu_kb
from src.keyboards.ai_keyboard import ai_settings_kb
from src.keyboards.inline import admin_menu_kb, rewrite_modes_kb, post_actions_kb
from src.models.channel import Channel
from src.models.media_item import MediaItem
from src.models.post import Post
from src.states.admin_states import AdminStates
from src.userbot.client import userbot
from src.utils.db import session
from src.utils.ai import is_enabled, rewrite_text, get_model
from src.utils.utils import safe_delete_message

router = Router()


@router.callback_query(F.data.startswith("adm:"))
async def admin_callbacks(c: CallbackQuery, state: FSMContext, db: AsyncSession):
    cmd = c.data.split(":")[1]

    if cmd == "sources":
        await state.clear()
        await c.message.edit_text(
            "📡 <b>Источники для мониторинга</b>\n\n"
            "Юзербот следит за этими каналами.",
            reply_markup=sources_menu_kb(),
            parse_mode="HTML"
        )
        await c.answer()
        return

    if cmd == "ai_settings":
        await state.clear()
        model = await get_model()
        await c.message.edit_text(
            f"⚙️ <b>Настройки AI</b>\n\n"
            f"Текущая модель: <code>{model}</code>\n\n"
            f"Выберите действие:",
            reply_markup=ai_settings_kb(),
            parse_mode="HTML"
        )
        await c.answer()
        return

    if cmd == "set_target":
        await state.set_state(AdminStates.wait_target_forward)
        await c.message.edit_text(
            "Перешли мне любой пост ИЗ канала, куда будем публиковать.\n"
            "Важно: юзербот должен быть админом там."
        )
        await c.answer()
        return

    if cmd == "list_links":
        target = (await db.execute(
            select(Channel).where(Channel.role == "target", Channel.is_active == True))).scalars().first()

        sources = (await db.execute(
            select(Channel).where(Channel.role == "source", Channel.is_active == True))).scalars().all()

        text = "🔌 Подключения:\n\n"
        text += f"🎯 Target: {target.chat_id if target else 'не задан'}\n\n"
        text += f"📡 Источников: {len(sources)}"

        await c.message.edit_text(text, reply_markup=admin_menu_kb())
        await c.answer()
        return


@router.callback_query(F.data.startswith("p:"))
async def post_callbacks(c: CallbackQuery, bot: Bot, db: AsyncSession):
    parts = c.data.split(":")
    if len(parts) < 3:
        await c.answer("Некорректно", show_alert=True)
        return

    post_id = int(parts[1])
    action = parts[2]

    if action == "rewrite":
        if not is_enabled():
            await c.answer("ANTHROPIC_API_KEY не задан", show_alert=True)
            return
        await c.message.edit_reply_markup(reply_markup=rewrite_modes_kb(post_id))
        await c.answer()
        return

    if action == "back":
        await c.message.edit_reply_markup(reply_markup=post_actions_kb(post_id))
        await c.answer()
        return

    # ─────────────────────────────────────────────────────────────
    # ПЕРЕПИСАТЬ → ОПУБЛИКОВАТЬ → УДАЛИТЬ
    # ─────────────────────────────────────────────────────────────



    if action == "rw":
        mode = parts[3] if len(parts) > 3 else "std"

        if not is_enabled():
            await c.answer("ANTHROPIC_API_KEY не задан", show_alert=True)
            return

        await c.answer("⏳ Переписываю и публикую…")

        admin_id = c.from_user.id
        message_id = c.message.message_id

        async def job():
            try:
                async with session() as s:
                    post = await s.get(Post, post_id)
                    if not post:
                        await bot.send_message(admin_id, f"❌ Пост #{post_id} не найден")
                        return

                    # Переписываем
                    rewritten = await rewrite_text(post.original_text or "", mode)

                    # Получаем target
                    target = (await s.execute(
                        select(Channel).where(Channel.role == "target", Channel.is_active == True)
                    )).scalars().first()

                    if not target:
                        await bot.send_message(admin_id, "❌ Target не задан")
                        return

                    # Получаем медиа
                    media_items = (await s.execute(
                        select(MediaItem).where(MediaItem.post_id == post_id).order_by(MediaItem.sort_index.asc())
                    )).scalars().all()

                    # Публикуем
                    success = await publish_via_userbot(
                        target.chat_id,
                        rewritten.strip(),
                        post.source_chat_id,
                        post.source_message_id,
                        bool(media_items)
                    )

                    if success:
                        await s.delete(post)
                        await s.commit()
                        await safe_delete_message(bot, admin_id, message_id)
                    else:
                        await bot.send_message(admin_id, "❌ Ошибка публикации")

            except Exception as e:
                await bot.send_message(admin_id, f"❌ Ошибка: {e}")

        asyncio.create_task(job())
        return

    # ─────────────────────────────────────────────────────────────
    # УДАЛИТЬ
    # ─────────────────────────────────────────────────────────────
    if action == "delete":
        post = await db.get(Post, post_id)
        if post:
            await db.delete(post)
            await db.commit()

        await safe_delete_message(bot, c.from_user.id, c.message.message_id)
        await c.answer("🗑 Удалено")
        return

    # ─────────────────────────────────────────────────────────────
    # ОПУБЛИКОВАТЬ (без переписывания)
    # ─────────────────────────────────────────────────────────────
    if action == "publish":
        post = await db.get(Post, post_id)
        if not post:
            await c.answer("Пост не найден", show_alert=True)
            return

        target = (await db.execute(
            select(Channel).where(Channel.role == "target", Channel.is_active == True)
        )).scalars().first()

        if not target:
            await c.answer("Target не задан", show_alert=True)
            return

        media_items = (await db.execute(
            select(MediaItem).where(MediaItem.post_id == post_id)
        )).scalars().all()

        text = (post.rewritten_text or post.original_text or "").strip()

        success = await publish_via_userbot(
            target.chat_id,
            text,
            post.source_chat_id,
            post.source_message_id,
            bool(media_items)
        )

        if success:
            await db.delete(post)
            await db.commit()
            await safe_delete_message(bot, c.from_user.id, c.message.message_id)
            await c.answer("✅ Опубликовано")
        else:
            await c.answer("❌ Ошибка", show_alert=True)
        return


# ─────────────────────────────────────────────────────────────
# Публикация через юзербот
# ─────────────────────────────────────────────────────────────

async def publish_via_userbot(
        target_chat_id: int,
        text: str,
        source_chat_id: int,
        source_message_id: int,
        has_media: bool
) -> bool:
    """
    Публикует через юзербот.
    Если есть медиа — копирует из источника с новым текстом.
    """
    import logging
    logger = logging.getLogger(__name__)

    if not userbot.is_connected:
        logger.error("Userbot not connected")
        return False

    try:
        if has_media and source_chat_id and source_message_id:
            # Получаем оригинал из источника
            msg = await userbot.client.get_messages(source_chat_id, ids=source_message_id)

            if msg and msg.media:
                # Отправляем с новым текстом
                await userbot.client.send_file(
                    target_chat_id,
                    msg.media,
                    caption=text,
                    parse_mode="html"
                )
                logger.info(f"Published with media to {target_chat_id}")
                return True

        # Только текст
        if len(text) <= 4096:
            await userbot.client.send_message(target_chat_id, text, parse_mode="html")
        else:
            for i in range(0, len(text), 4096):
                await userbot.client.send_message(target_chat_id, text[i:i + 4096], parse_mode="html")

        logger.info(f"Published text to {target_chat_id}")
        return True

    except Exception as e:
        logger.error(f"Publish failed: {e}")
        return False

