"""
src/handlers/admin/callback.py
Хендлеры кнопок — переписать/удалить/опубликовать
"""

import asyncio
import logging
import re

from aiogram import Router, Bot, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, BufferedInputFile, InputMediaPhoto, InputMediaVideo, InputMediaDocument

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.keyboards.admin_channels import sources_menu_kb
from src.keyboards.ai_keyboard import ai_settings_kb
from src.keyboards.inline import admin_menu_kb, rewrite_modes_kb, post_actions_kb, preview_actions_kb
from src.models.channel import Channel
from src.models.media_item import MediaItem
from src.models.post import Post
from src.states.admin_states import AdminStates
from src.userbot.client import userbot
from src.userbot.publisher import publish_post
from src.utils.db import session
from src.utils.ai import is_enabled, rewrite_text, get_model
from src.utils.utils import safe_delete_message

router = Router()
logger = logging.getLogger(__name__)


def clean_ai_markdown_links(text: str) -> str:
    """
    Убирает markdown ссылки которые генерирует AI.
    Применяется ТОЛЬКО к переписанному тексту.
    """
    if not text:
        return text

    # [текст](url) → текст
    text = re.sub(r'\[([^\]]+)\]\(https?://[^)]+\)', r'\1', text)

    # [слово]https://... → слово (без пробела)
    text = re.sub(r'\[([^\]]+)\]https?://\S+', r'\1', text)

    # [слово] https://... → слово (с пробелом)
    text = re.sub(r'\[([^\]]+)\]\s+https?://\S+', r'\1', text)

    # Оставшиеся [слово] перед URL на новой строке
    text = re.sub(r'\[([^\]]+)\]\n\s*https?://\S+', r'\1', text)

    # Просто [слово] без ссылки — убираем скобки
    text = re.sub(r'\[([^\]]+)\](?!\()', r'\1', text)

    return text


def has_real_file(msg) -> bool:
    """Проверяет, есть ли реальный файл"""
    from telethon.tl.types import MessageMediaWebPage
    if not msg or not msg.media:
        return False
    if isinstance(msg.media, MessageMediaWebPage):
        return False
    return bool(msg.photo or msg.video or msg.document or msg.audio or msg.voice)


async def delete_preview(bot: Bot, user_id: int, state: FSMContext):
    """Удаляет все сообщения превью"""
    data = await state.get_data()
    preview_msg_ids = data.get("preview_msg_ids", [])

    for msg_id in preview_msg_ids:
        await safe_delete_message(bot, user_id, msg_id)

    await state.update_data(preview_msg_ids=[])


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
async def post_callbacks(c: CallbackQuery, bot: Bot, db: AsyncSession, state: FSMContext):
    parts = c.data.split(":")
    if len(parts) < 3:
        await c.answer("Некорректно", show_alert=True)
        return

    post_id = int(parts[1])
    action = parts[2]

    # ─────────────────────────────────────────────────────────────
    # ВЫБОР РЕЖИМА ПЕРЕПИСЫВАНИЯ
    # ─────────────────────────────────────────────────────────────
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
    # ПЕРЕПИСАТЬ → ПОКАЗАТЬ ПРЕВЬЮ
    # ─────────────────────────────────────────────────────────────
    if action == "rw":
        mode = parts[3] if len(parts) > 3 else "std"

        if not is_enabled():
            await c.answer("ANTHROPIC_API_KEY не задан", show_alert=True)
            return

        await c.answer("⏳ Переписываю...")

        admin_id = c.from_user.id
        buttons_msg_id = c.message.message_id

        async def job():
            try:
                # Удаляем старое превью
                await delete_preview(bot, admin_id, state)

                # Удаляем сообщение с кнопками
                await safe_delete_message(bot, admin_id, buttons_msg_id)

                async with session() as s:
                    post = await s.get(Post, post_id)
                    if not post:
                        await bot.send_message(admin_id, f"❌ Пост #{post_id} не найден")
                        return

                    # Переписываем
                    rewritten = await rewrite_text(post.original_text or "", mode)
                    # Очищаем ТОЛЬКО переписанный текст от markdown ссылок
                    rewritten = clean_ai_markdown_links(rewritten.strip())

                    # Сохраняем переписанный текст
                    post.rewritten_text = rewritten
                    await s.commit()

                    # Получаем медиа
                    media_result = await s.execute(
                        select(MediaItem).where(MediaItem.post_id == post_id).order_by(MediaItem.sort_index.asc())
                    )
                    media_items = media_result.scalars().all()
                    has_media = bool(media_items)

                    # Отправляем НОВОЕ превью с ПЕРЕПИСАННЫМ текстом
                    new_preview_ids = await send_preview_via_bot(
                        bot,
                        admin_id,
                        rewritten,
                        post.source_chat_id,
                        post.source_message_id,
                        has_media
                    )

                    # Сохраняем ID нового превью
                    await state.update_data(preview_msg_ids=new_preview_ids)

                    # Отправляем кнопки
                    await bot.send_message(
                        admin_id,
                        "👆 <b>Превью переписанного поста</b>\n\nОпубликовать?",
                        reply_markup=preview_actions_kb(post_id),
                        parse_mode="HTML"
                    )

            except Exception as e:
                logger.exception(f"Rewrite job error: {e}")
                await bot.send_message(admin_id, f"❌ Ошибка: {e}")

        asyncio.create_task(job())
        return

    # ─────────────────────────────────────────────────────────────
    # УДАЛИТЬ
    # ─────────────────────────────────────────────────────────────
    if action == "delete":
        # Удаляем превью
        await delete_preview(bot, c.from_user.id, state)

        # Удаляем пост из БД
        post = await db.get(Post, post_id)
        if post:
            await db.delete(post)
            await db.commit()

        # Удаляем сообщение с кнопками
        await safe_delete_message(bot, c.from_user.id, c.message.message_id)

        await c.answer("🗑 Удалено")
        return

    # ─────────────────────────────────────────────────────────────
    # ОПУБЛИКОВАТЬ
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

        # Если есть переписанный текст — используем его (уже очищен)
        # Если нет — используем оригинал БЕЗ изменений
        if post.rewritten_text:
            text = post.rewritten_text.strip()
        else:
            text = (post.original_text or "").strip()

        await c.answer("⏳ Публикую...")

        success = await publish_post(
            userbot.client,
            target.chat_id,
            text,
            post.source_chat_id,
            post.source_message_id,
            bool(media_items)
        )

        if success:
            # Удаляем превью
            await delete_preview(bot, c.from_user.id, state)

            # Удаляем пост из БД
            await db.delete(post)
            await db.commit()

            # Удаляем сообщение с кнопками
            await safe_delete_message(bot, c.from_user.id, c.message.message_id)

            await c.answer("✅ Опубликовано!")
        else:
            await c.answer("❌ Ошибка публикации", show_alert=True)
        return

    # ─────────────────────────────────────────────────────────────
    # ОТМЕНА (вернуться к оригиналу)
    # ─────────────────────────────────────────────────────────────
    if action == "cancel":
        # Удаляем превью
        await delete_preview(bot, c.from_user.id, state)

        # Удаляем текущее сообщение с кнопками
        await safe_delete_message(bot, c.from_user.id, c.message.message_id)

        # Очищаем переписанный текст
        post = await db.get(Post, post_id)
        if post:
            post.rewritten_text = None
            await db.commit()

            # Отправляем оригинал заново
            media_items = (await db.execute(
                select(MediaItem).where(MediaItem.post_id == post_id)
            )).scalars().all()

            original_preview_ids = await send_preview_via_bot(
                bot,
                c.from_user.id,
                post.original_text or "",
                post.source_chat_id,
                post.source_message_id,
                bool(media_items)
            )

            await state.update_data(preview_msg_ids=original_preview_ids)

            # Отправляем кнопки
            await bot.send_message(
                c.from_user.id,
                "👆 <b>Оригинальный пост</b>\n\nВыберите действие:",
                reply_markup=post_actions_kb(post_id),
                parse_mode="HTML"
            )

        await c.answer()
        return


async def send_preview_via_bot(bot: Bot, admin_id: int, text: str, source_chat_id: int, source_message_id: int, has_media: bool) -> list[int]:
    """
    Отправляет превью поста админу через бота.
    Возвращает список ID отправленных сообщений.
    """
    msg_ids = []

    try:
        if has_media and source_chat_id and source_message_id and userbot.client:
            msg = await userbot.client.get_messages(source_chat_id, ids=source_message_id)

            if msg and msg.grouped_id:
                # Альбом
                grouped_id = msg.grouped_id
                messages = await userbot.client.get_messages(
                    source_chat_id,
                    limit=15,
                    max_id=msg.id + 10,
                    min_id=msg.id - 5
                )
                album_msgs = [m for m in messages if m.grouped_id == grouped_id and has_real_file(m)]
                album_msgs.sort(key=lambda m: m.id)

                if album_msgs:
                    media_group = []
                    for i, m in enumerate(album_msgs):
                        file_bytes = await userbot.client.download_media(m, file=bytes)
                        if file_bytes:
                            caption = text[:1024] if i == 0 and text else None
                            input_file = BufferedInputFile(file_bytes, filename=f"media_{i}")

                            if m.photo:
                                media_group.append(InputMediaPhoto(media=input_file, caption=caption, parse_mode="HTML"))
                            elif m.video:
                                media_group.append(InputMediaVideo(media=input_file, caption=caption, parse_mode="HTML"))
                            else:
                                media_group.append(InputMediaDocument(media=input_file, caption=caption, parse_mode="HTML"))

                    if media_group:
                        result = await bot.send_media_group(admin_id, media_group)
                        msg_ids.extend([m.message_id for m in result])

                        if text and len(text) > 1024:
                            text_msg = await bot.send_message(
                                admin_id, text, parse_mode="HTML", disable_web_page_preview=True
                            )
                            msg_ids.append(text_msg.message_id)

                        return msg_ids

            elif msg and has_real_file(msg):
                # Одиночное медиа
                file_bytes = await userbot.client.download_media(msg, file=bytes)
                if file_bytes:
                    input_file = BufferedInputFile(file_bytes, filename="media")
                    caption = text[:1024] if text else None

                    if msg.photo:
                        result = await bot.send_photo(admin_id, input_file, caption=caption, parse_mode="HTML")
                    elif msg.video:
                        result = await bot.send_video(admin_id, input_file, caption=caption, parse_mode="HTML")
                    else:
                        result = await bot.send_document(admin_id, input_file, caption=caption, parse_mode="HTML")

                    msg_ids.append(result.message_id)

                    if text and len(text) > 1024:
                        text_msg = await bot.send_message(
                            admin_id, text, parse_mode="HTML", disable_web_page_preview=True
                        )
                        msg_ids.append(text_msg.message_id)

                    return msg_ids

        # Только текст
        if text:
            result = await bot.send_message(
                admin_id, text, parse_mode="HTML", disable_web_page_preview=True
            )
            msg_ids.append(result.message_id)

    except Exception as e:
        logger.error(f"Failed to send preview: {e}")

    return msg_ids