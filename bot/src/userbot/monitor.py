"""
src/userbot/monitor.py
Мониторинг каналов-источников
"""

import asyncio
import json
import logging

from aiogram import Bot
from telethon.tl.types import Channel as TelethonChannel, Message, MessageMediaWebPage

from sqlalchemy import select, update

from telethon import TelegramClient

from src.keyboards.inline import post_actions_kb
from src.utils.tg_format import md_to_html, split_html_safe, split_caption_and_tail

from src.models.channel import Channel
from src.models.media_item import MediaItem
from src.models.post import Post
from src.utils.config import settings
from src.utils.db import session

logger = logging.getLogger(__name__)


class ChannelMonitor:
    """Мониторит каналы-источники и сохраняет посты в БД"""

    def __init__(self):
        self._sources_cache: dict[int, Channel] = {}
        self._cache_updated = 0
        self._cache_ttl = 30
        self._bot: Bot | None = None
        self._client: TelegramClient | None = None

        # Буфер для альбомов
        self._album_buf: dict[str, dict] = {}
        self._album_tasks: dict[str, asyncio.Task] = {}

    def _has_real_file(self, msg) -> bool:
        from telethon.tl.types import MessageMediaWebPage
        if not msg:
            return False
        if isinstance(getattr(msg, "media", None), MessageMediaWebPage):
            return False
        return bool(msg.photo or msg.video or msg.document or msg.audio or msg.voice)

    async def _send_preview_to_admin(
            self,
            admin_id: int,
            text: str,
            source_chat_id: int,
            source_message_id: int,
            has_media: bool
    ) -> list[int]:
        msg_ids: list[int] = []

        # если нет telethon-клиента — падаем в режим "только текст"
        client = self._client

        html_text = md_to_html(text)
        caption, tail = split_caption_and_tail(html_text, caption_limit=1024)

        try:
            if has_media and client and source_chat_id and source_message_id:
                msg = await client.get_messages(source_chat_id, ids=source_message_id)

                # альбом
                if msg and msg.grouped_id:
                    grouped_id = msg.grouped_id
                    messages = await client.get_messages(
                        source_chat_id, limit=15, max_id=msg.id + 10, min_id=msg.id - 5
                    )
                    album_msgs = [m for m in messages if m.grouped_id == grouped_id and self._has_real_file(m)]
                    album_msgs.sort(key=lambda m: m.id)

                    if album_msgs:
                        from aiogram.types import BufferedInputFile, InputMediaPhoto, InputMediaVideo, \
                            InputMediaDocument

                        media_group = []
                        for i, m in enumerate(album_msgs):
                            file_bytes = await client.download_media(m, file=bytes)
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
                            result = await self._bot.send_media_group(admin_id, media_group)
                            msg_ids.extend([m.message_id for m in result])

                            for chunk in split_html_safe(tail, limit=4096):
                                m = await self._bot.send_message(admin_id, chunk, parse_mode="HTML",
                                                                 disable_web_page_preview=True)
                                msg_ids.append(m.message_id)

                            return msg_ids

                # одиночное медиа
                if msg and self._has_real_file(msg):
                    from aiogram.types import BufferedInputFile

                    file_bytes = await client.download_media(msg, file=bytes)
                    if file_bytes:
                        input_file = BufferedInputFile(file_bytes, filename="media")

                        if msg.photo:
                            res = await self._bot.send_photo(admin_id, input_file, caption=caption or None,
                                                             parse_mode="HTML")
                        elif msg.video:
                            res = await self._bot.send_video(admin_id, input_file, caption=caption or None,
                                                             parse_mode="HTML")
                        else:
                            res = await self._bot.send_document(admin_id, input_file, caption=caption or None,
                                                                parse_mode="HTML")

                        msg_ids.append(res.message_id)

                        for chunk in split_html_safe(tail, limit=4096):
                            m = await self._bot.send_message(admin_id, chunk, parse_mode="HTML",
                                                             disable_web_page_preview=True)
                            msg_ids.append(m.message_id)

                        return msg_ids

            # только текст
            for chunk in split_html_safe(html_text, limit=4096):
                m = await self._bot.send_message(admin_id, chunk, parse_mode="HTML", disable_web_page_preview=True)
                msg_ids.append(m.message_id)

        except Exception as e:
            logger.error(f"Failed to send preview to admin: {e}")

        return msg_ids

    def set_bot(self, bot: Bot):
        self._bot = bot
        logger.info("Bot set for notifications")

    def set_client(self, client: TelegramClient):
        self._client = client
        logger.info("Telethon client set for preview sending")

    def invalidate_cache(self):
        self._cache_updated = 0
        logger.info("Sources cache invalidated")

    async def update_cache(self):
        """Обновить кеш источников"""
        now = asyncio.get_event_loop().time()
        if now - self._cache_updated < self._cache_ttl:
            return

        async with session() as s:
            result = await s.execute(
                select(Channel).where(
                    Channel.role == "source",
                    Channel.is_active == True
                )
            )
            sources = result.scalars().all()

            self._sources_cache = {}
            for src in sources:
                self._sources_cache[src.chat_id] = src
                if src.chat_id < 0:
                    telethon_id = int(str(src.chat_id).replace("-100", ""))
                    self._sources_cache[telethon_id] = src

        self._cache_updated = now
        logger.info(f"Sources cache updated: {len(sources)} active sources")

    async def get_source(self, chat: TelethonChannel) -> Channel | None:
        """Найти источник по чату"""
        await self.update_cache()

        if chat.id in self._sources_cache:
            return self._sources_cache[chat.id]

        bot_format_id = -int(f"100{chat.id}")
        if bot_format_id in self._sources_cache:
            return self._sources_cache[bot_format_id]

        return None

    @staticmethod
    def is_webpage(msg: Message) -> bool:
        return isinstance(getattr(msg, "media", None), MessageMediaWebPage)

    @staticmethod
    def has_real_file(msg: Message) -> bool:
        """Проверяет, есть ли реальный файл"""
        if ChannelMonitor.is_webpage(msg):
            return False
        return bool(msg.photo or msg.video or msg.document or msg.audio or msg.voice)

    async def on_message(self, chat: TelethonChannel, message: Message):
        """Обработать новое сообщение из канала"""
        source = await self.get_source(chat)
        if not source:
            return

        logger.info(f"📨 New post in SOURCE: {chat.title} (id={chat.id}, msg_id={message.id})")

        # Обновляем title
        if chat.title and chat.title != source.title:
            async with session() as s:
                await s.execute(
                    update(Channel)
                    .where(Channel.id == source.id)
                    .values(title=chat.title)
                )
                await s.commit()

        # ID в формате бота
        bot_chat_id = -int(f"100{chat.id}")
        text = message.text or message.message or ""
        group_id = message.grouped_id

        if group_id:
            await self._handle_album(bot_chat_id, message.id, str(group_id), text, message)
        else:
            await self._save_single_post(bot_chat_id, message.id, text, message)

    async def _handle_album(self, chat_id: int, msg_id: int, group_id: str, text: str, message: Message):
        """Обработка альбома"""
        key = f"{chat_id}:{group_id}"

        if key not in self._album_buf:
            self._album_buf[key] = {
                "chat_id": chat_id,
                "group_id": group_id,
                "first_msg_id": msg_id,
                "text": text or "",
                "media_msg_ids": [],
            }

        buf = self._album_buf[key]
        buf["first_msg_id"] = min(buf["first_msg_id"], msg_id)

        if text and not buf["text"]:
            buf["text"] = text

        if self.has_real_file(message):
            buf["media_msg_ids"].append(msg_id)

        old = self._album_tasks.get(key)
        if old and not old.done():
            old.cancel()
        self._album_tasks[key] = asyncio.create_task(self._flush_album(key))

    async def _flush_album(self, key: str):
        """Сохранить альбом в БД"""
        await asyncio.sleep(2.5)

        buf = self._album_buf.pop(key, None)
        self._album_tasks.pop(key, None)

        if not buf:
            return

        logger.info(f"💾 Saving album: {len(buf['media_msg_ids'])} items")

        try:
            async with session() as s:
                post = Post(
                    source_chat_id=buf["chat_id"],
                    source_message_id=buf["first_msg_id"],
                    media_group_id=buf["group_id"],
                    original_text=buf["text"] or "",
                    notified=0,
                )
                s.add(post)
                await s.flush()

                for idx, mid in enumerate(sorted(buf["media_msg_ids"])):
                    s.add(MediaItem(
                        post_id=post.id,
                        kind="media",
                        file_id=str(mid),
                        sort_index=idx
                    ))

                await s.commit()
                logger.info(f"✅ Album saved: Post #{post.id}")

            await self._notify_admins(post.id, buf["text"], len(buf["media_msg_ids"]), buf["chat_id"], buf["first_msg_id"])

        except Exception as e:
            logger.exception(f"❌ Failed to save album: {e}")

    async def _save_single_post(self, chat_id: int, msg_id: int, text: str, message: Message):
        """Сохранить одиночный пост"""
        has_file = self.has_real_file(message)

        logger.info(f"💾 Saving single post: msg_id={msg_id}, has_file={has_file}")

        try:
            async with session() as s:
                post = Post(
                    source_chat_id=chat_id,
                    source_message_id=msg_id,
                    media_group_id=None,
                    original_text=text or "",
                    notified=0,
                )
                s.add(post)
                await s.flush()

                if has_file:
                    s.add(MediaItem(
                        post_id=post.id,
                        kind="media",
                        file_id=str(msg_id),
                        sort_index=0
                    ))

                await s.commit()
                logger.info(f"✅ Post saved: #{post.id}")

            await self._notify_admins(post.id, text, 1 if has_file else 0, chat_id, msg_id)

        except Exception as e:
            logger.exception(f"❌ Failed to save post: {e}")

    async def _notify_admins(
            self,
            post_id: int,
            text: str,
            media_count: int,
            source_chat_id: int,
            source_message_id: int
    ):
        """Уведомить админов — сразу пост + кнопки + сохранить msg_id в БД"""
        if not self._bot:
            logger.warning("Bot not set!")
            return

        for admin_id in settings.ADMIN_IDS:
            try:
                # 1) Отправляем превью поста (текст/медиа/альбом) и получаем message_id(ы)
                preview_ids = await self._send_preview_to_admin(
                    admin_id=admin_id,
                    text=text or "",
                    source_chat_id=source_chat_id,
                    source_message_id=source_message_id,
                    has_media=media_count > 0
                )

                anchor = preview_ids[0] if preview_ids else None

                # 2) Отправляем сообщение с кнопками (отдельно, потому что у альбома нельзя inline-кнопки)
                ctrl = await self._bot.send_message(
                    admin_id,
                    "Выберите действие:",
                    reply_markup=post_actions_kb(post_id),
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_to_message_id=anchor
                )

                # 3) Сохраняем IDs сообщений в БД, чтобы потом удалить превью полностью
                async with session() as s:
                    post = await s.get(Post, post_id)
                    if post:
                        post.preview_msg_ids = json.dumps(preview_ids)  # строка JSON: [123,124,...]
                        post.control_msg_id = int(ctrl.message_id)
                        await s.commit()

                logger.info(f"📤 Sent post preview to admin {admin_id} for post #{post_id}")

            except Exception as e:
                logger.exception(f"Failed to notify {admin_id}: {e}")


# Глобальный экземпляр
monitor = ChannelMonitor()