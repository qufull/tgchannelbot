"""
src/userbot/monitor.py
Мониторинг каналов-источников
"""

import asyncio
import logging

from aiogram import Bot
from telethon.tl.types import Channel as TelethonChannel, Message, MessageMediaWebPage

from sqlalchemy import select, update

from src.keyboards.inline import new_post_notice_kb
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

        # Буфер для альбомов
        self._album_buf: dict[str, dict] = {}
        self._album_tasks: dict[str, asyncio.Task] = {}

    def set_bot(self, bot: Bot):
        self._bot = bot
        logger.info("Bot set for notifications")

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
        """Уведомить админов — ТОЛЬКО уведомление + кнопки (без медиа/текста)"""
        if not self._bot:
            logger.warning("Bot not set!")
            return

        from src.keyboards.inline import post_actions_kb

        # короткая служебка (без парсинга HTML из текста поста)
        msg = (
            "🆕 <b>Новый пост</b>\n"
            f"📎 Вложений: <b>{media_count}</b>\n"
        )

        for admin_id in settings.ADMIN_IDS:
            try:
                await self._bot.send_message(
                    admin_id,
                    msg,
                    reply_markup=new_post_notice_kb(post_id),
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                logger.info(f"📤 Notified admin {admin_id} about post #{post_id}")
            except Exception as e:
                logger.error(f"Failed to notify {admin_id}: {e}")


# Глобальный экземпляр
monitor = ChannelMonitor()