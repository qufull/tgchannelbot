"""
src/handlers/admin/callback.py
Хендлеры кнопок — переписать/удалить/опубликовать
"""

import asyncio
import json
import logging

from aiogram import Router, Bot, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, BufferedInputFile, InputMediaPhoto, InputMediaVideo, InputMediaDocument

from sqlalchemy import select, delete
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
from src.utils.tg_format import md_to_html, split_html_safe, split_caption_and_tail
from src.utils.utils import safe_delete_message

router = Router()
logger = logging.getLogger(__name__)

def has_real_file(msg) -> bool:
    """Проверяет, есть ли реальный файл"""
    from telethon.tl.types import MessageMediaWebPage
    if not msg or not msg.media:
        return False
    if isinstance(msg.media, MessageMediaWebPage):
        return False
    return bool(msg.photo or msg.video or msg.document or msg.audio or msg.voice)


async def delete_preview(bot: Bot, user_id: int, state: FSMContext, skip_msg_id: int | None = None):
    data = await state.get_data()
    preview_msg_ids = data.get("preview_msg_ids", [])
    control_msg_ids = data.get("control_msg_ids", [])

    for msg_id in list(dict.fromkeys(preview_msg_ids + control_msg_ids)):
        await safe_delete_message(bot, user_id, msg_id)

    await state.update_data(preview_msg_ids=[], control_msg_ids=[])



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

    if action == "open":
        admin_id = c.from_user.id
        notify_msg_id = c.message.message_id

        await c.answer()

        # чистим любой старый UI
        await delete_preview(bot, c.from_user.id, state, skip_msg_id=c.message.message_id)

        # удаляем само уведомление
        await safe_delete_message(bot, admin_id, notify_msg_id)

        post = await db.get(Post, post_id)
        if not post:
            await bot.send_message(admin_id, f"❌ Пост #{post_id} не найден")
            return

        media_items = (await db.execute(
            select(MediaItem).where(MediaItem.post_id == post_id).order_by(MediaItem.sort_index.asc())
        )).scalars().all()
        has_media = bool(media_items)

        preview_ids = await send_preview_via_bot(
            bot=bot,
            admin_id=admin_id,
            text=(post.original_text or "").strip(),
            source_chat_id=post.source_chat_id,
            source_message_id=post.source_message_id,
            has_media=has_media
        )
        await state.update_data(preview_msg_ids=preview_ids)

        anchor = preview_ids[0] if preview_ids else None
        ctrl = await bot.send_message(
            admin_id,
            "👆 <b>Оригинальный пост</b>\n\nВыберите действие:",
            reply_markup=post_actions_kb(post_id),
            parse_mode="HTML",
            reply_to_message_id=anchor
        )
        await state.update_data(control_msg_ids=[ctrl.message_id])
        return

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

        admin_id = c.from_user.id
        buttons_msg_id = c.message.message_id

        # ✅ СРАЗУ удаляем сообщение с выбором режима (чтобы не висело)
        await safe_delete_message(bot, admin_id, buttons_msg_id)

        await c.answer("⏳ Переписываю...")

        async def job():
            try:
                # 1) Чистим старые превью (если они были из open-режима)
                await delete_preview(bot, admin_id, state)

                async with session() as s:
                    post = await s.get(Post, post_id)
                    if not post:
                        await bot.send_message(admin_id, f"❌ Пост #{post_id} не найден")
                        return

                    # 2) Переписываем
                    rewritten = await rewrite_text(post.original_text or "", mode)
                    rewritten = md_to_html(rewritten)

                    post.rewritten_text = rewritten
                    await s.commit()

                    # 3) Медиа
                    media_result = await s.execute(
                        select(MediaItem).where(MediaItem.post_id == post_id).order_by(MediaItem.sort_index.asc())
                    )
                    media_items = media_result.scalars().all()
                    has_media = bool(media_items)

                    # 4) Отправляем превью переписанного
                    new_preview_ids = await send_preview_via_bot(
                        bot,
                        admin_id,
                        rewritten,
                        post.source_chat_id,
                        post.source_message_id,
                        has_media
                    )
                    await state.update_data(preview_msg_ids=new_preview_ids)

                    # 5) Кнопки publish/cancel
                    ctrl = await bot.send_message(
                        admin_id,
                        "👆 <b>Превью переписанного поста</b>\n\nОпубликовать?",
                        reply_markup=preview_actions_kb(post_id),
                        parse_mode="HTML"
                    )
                    await state.update_data(control_msg_ids=[ctrl.message_id])

            except Exception as e:
                logger.exception(f"Rewrite job error: {e}")
                await bot.send_message(admin_id, f"❌ Ошибка: {e}")

        asyncio.create_task(job())
        return

    # ─────────────────────────────────────────────────────────────
    # УДАЛИТЬ
    # ─────────────────────────────────────────────────────────────
    if action == "delete":
        post = await db.get(Post, post_id)
        if post:
            # 🔥 удалить превью поста
            if post.preview_msg_ids:
                for mid in json.loads(post.preview_msg_ids):
                    await safe_delete_message(bot, c.from_user.id, int(mid))

            # 🔥 удалить кнопки
            if post.control_msg_id:
                await safe_delete_message(bot, c.from_user.id, post.control_msg_id)

            # 🔥 удалить медиа из БД
            await db.execute(delete(MediaItem).where(MediaItem.post_id == post_id))

            # 🔥 удалить сам пост
            await db.delete(post)
            await db.commit()

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
            admin_id = c.from_user.id

            # 1) удалить превью поста (сообщения, которые бот прислал админу)
            if post.preview_msg_ids:
                try:
                    for mid in json.loads(post.preview_msg_ids):
                        await safe_delete_message(bot, admin_id, int(mid))
                except Exception as e:
                    logger.error(f"Failed to delete preview msgs for post #{post_id}: {e}")

            # 2) удалить сообщение с кнопками "Выберите действие" (которое создал monitor)
            if post.control_msg_id:
                await safe_delete_message(bot, admin_id, int(post.control_msg_id))

            # 3) удалить возможные FSM-превью (переписанный вариант), если было
            await delete_preview(bot, admin_id, state)

            # 4) удалить текущее сообщение callback (на всякий случай)
            await safe_delete_message(bot, admin_id, c.message.message_id)

            # 5) удалить пост из БД (media_items удалятся каскадом, но можно оставить как есть)
            await db.delete(post)
            await db.commit()

            await c.answer("✅ Опубликовано!")
        else:
            await c.answer("❌ Ошибка публикации", show_alert=True)

        return

    # ─────────────────────────────────────────────────────────────
    # ОТМЕНА (вернуться к оригиналу)
    # ─────────────────────────────────────────────────────────────
    if action == "cancel":
        # Удаляем превью
        await delete_preview(bot, c.from_user.id, state, skip_msg_id=c.message.message_id)

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
    msg_ids: list[int] = []

    try:
        html_text = md_to_html(text)
        caption, tail = split_caption_and_tail(html_text, caption_limit=1024)

        if has_media and source_chat_id and source_message_id and userbot.client:
            msg = await userbot.client.get_messages(source_chat_id, ids=source_message_id)

            if msg and msg.grouped_id:
                grouped_id = msg.grouped_id
                messages = await userbot.client.get_messages(
                    source_chat_id, limit=15, max_id=msg.id + 10, min_id=msg.id - 5
                )
                album_msgs = [m for m in messages if m.grouped_id == grouped_id and has_real_file(m)]
                album_msgs.sort(key=lambda m: m.id)

                if album_msgs:
                    media_group = []
                    for i, m in enumerate(album_msgs):
                        file_bytes = await userbot.client.download_media(m, file=bytes)
                        if not file_bytes:
                            continue

                        input_file = BufferedInputFile(file_bytes, filename=f"media_{i}")
                        cap = caption if i == 0 and caption else None

                        if m.photo:
                            media_group.append(InputMediaPhoto(media=input_file, caption=cap, parse_mode="HTML"))
                        elif m.video:
                            media_group.append(InputMediaVideo(media=input_file, caption=cap, parse_mode="HTML"))
                        else:
                            media_group.append(InputMediaDocument(media=input_file, caption=cap, parse_mode="HTML"))

                    if media_group:
                        result = await bot.send_media_group(admin_id, media_group)
                        msg_ids.extend([m.message_id for m in result])

                        # хвост текста отдельными сообщениями (без ломания HTML)
                        for chunk in split_html_safe(tail, limit=4096):
                            m = await bot.send_message(admin_id, chunk, parse_mode="HTML", disable_web_page_preview=True)
                            msg_ids.append(m.message_id)

                        return msg_ids

            elif msg and has_real_file(msg):
                file_bytes = await userbot.client.download_media(msg, file=bytes)
                if file_bytes:
                    input_file = BufferedInputFile(file_bytes, filename="media")
                    if msg.photo:
                        res = await bot.send_photo(admin_id, input_file, caption=caption or None, parse_mode="HTML")
                    elif msg.video:
                        res = await bot.send_video(admin_id, input_file, caption=caption or None, parse_mode="HTML")
                    else:
                        res = await bot.send_document(admin_id, input_file, caption=caption or None, parse_mode="HTML")

                    msg_ids.append(res.message_id)

                    for chunk in split_html_safe(tail, limit=4096):
                        m = await bot.send_message(admin_id, chunk, parse_mode="HTML", disable_web_page_preview=True)
                        msg_ids.append(m.message_id)

                    return msg_ids

        # только текст
        for chunk in split_html_safe(html_text, limit=4096):
            m = await bot.send_message(admin_id, chunk, parse_mode="HTML", disable_web_page_preview=True)
            msg_ids.append(m.message_id)

    except Exception as e:
        logger.error(f"Failed to send preview: {e}")

    return msg_ids