"""
src/userbot/client.py
Юзербот мониторит источники → сохраняет в БД → уведомляет админов
"""

import asyncio
import logging

from aiogram import Bot
from telethon import TelegramClient, events
from telethon.tl.types import Channel as TelethonChannel, Message, MessageMediaWebPage

from sqlalchemy import select, update

from src.models.channel import Channel
from src.models.media_item import MediaItem
from src.models.post import Post
from src.utils.config import settings
from src.utils.db import session

logger = logging.getLogger(__name__)


class UserBot:
    def __init__(self):
        self.client: TelegramClient | None = None
        self._sources_cache: dict[int, Channel] = {}
        self._cache_updated = 0
        self._cache_ttl = 30
        self._bot: Bot | None = None  # Ссылка на aiogram бота для уведомлений

        # Буфер для альбомов
        self._album_buf: dict[str, dict] = {}
        self._album_tasks: dict[str, asyncio.Task] = {}

    def set_bot(self, bot: Bot):
        """Установить ссылку на aiogram бота"""
        self._bot = bot

    async def start(self):
        """Запуск юзербота"""
        self.client = TelegramClient(
            'userbot_session',
            settings.API_ID,
            settings.API_HASH
        )

        await self.client.start(phone=settings.PHONE)
        logger.info("Userbot connected")

        self.client.add_event_handler(
            self._on_channel_message,
            events.NewMessage()
        )

        logger.info("Userbot handlers registered")

    async def stop(self):
        """Остановка юзербота"""
        if self.client:
            await self.client.disconnect()
            logger.info("Userbot disconnected")

    async def run_until_disconnected(self):
        """Держим соединение"""
        if self.client:
            await self.client.run_until_disconnected()

    async def _update_cache(self):
        """Обновляем кеш источников из БД"""
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
        logger.debug(f"Sources cache: {len(sources)} active")

    async def _get_source(self, chat: TelethonChannel) -> Channel | None:
        """Найти источник по чату"""
        await self._update_cache()

        if chat.id in self._sources_cache:
            return self._sources_cache[chat.id]

        bot_format_id = -int(f"100{chat.id}")
        if bot_format_id in self._sources_cache:
            return self._sources_cache[bot_format_id]

        return None

    def is_webpage(self,msg: Message) -> bool:
        return isinstance(msg.media, MessageMediaWebPage)

    def has_real_file(self, msg: Message) -> bool:
        return bool(msg.photo or msg.video or msg.document or msg.audio or msg.voice)

    def _extract_media(self, msg: Message) -> tuple[str, str] | None:
        """Извлечь тип и file_id медиа"""
        if msg.photo:
            return "photo", str(msg.photo.id)
        if msg.video:
            return "video", str(msg.video.id)
        if msg.document:
            return "document", str(msg.document.id)
        if msg.audio:
            return "audio", str(msg.audio.id)
        return None

    async def _on_channel_message(self, event: events.NewMessage.Event):
        """Обработчик новых сообщений"""
        try:
            message: Message = event.message
            chat = await event.get_chat()

            if not isinstance(chat, TelethonChannel):
                return

            source = await self._get_source(chat)
            if not source:
                return

            logger.info(f"New post in {chat.title} (id={chat.id})")

            # Обновляем title
            if chat.title and chat.title != source.title:
                async with session() as s:
                    await s.execute(
                        update(Channel)
                        .where(Channel.id == source.id)
                        .values(title=chat.title)
                    )
                    await s.commit()

            # Конвертируем ID в формат бота
            bot_chat_id = -int(f"100{chat.id}")

            text = message.text or message.message or ""
            group_id = message.grouped_id

            # Альбом
            if group_id:
                await self._handle_album(bot_chat_id, message.id, str(group_id), text, message)
                return

            # Одиночное сообщение
            await self._save_single_post(bot_chat_id, message.id, text, message)

        except Exception as e:
            logger.exception(f"Error in channel handler: {e}")

    async def _handle_album(self, chat_id: int, msg_id: int, group_id: str, text: str):
        """Обработка альбома (группы медиа)"""
        key = f"{chat_id}:{group_id}"

        if key not in self._album_buf:
            self._album_buf[key] = {
                "chat_id": chat_id,
                "group_id": group_id,
                "first_msg_id": msg_id,
                "text": text,
                "media_msg_ids": [msg_id],
            }
        else:
            buf = self._album_buf[key]
            if msg_id < buf["first_msg_id"]:
                buf["first_msg_id"] = msg_id
            if text and not buf["text"]:
                buf["text"] = text
            buf["media_msg_ids"].append(msg_id)

        # Отменяем предыдущий таймер
        if key in self._album_tasks:
            self._album_tasks[key].cancel()

        # Запускаем новый таймер
        self._album_tasks[key] = asyncio.create_task(self._flush_album(key))

    async def _flush_album(self, key: str):
        """Сохранить альбом в БД после дебаунса"""
        await asyncio.sleep(1.5)

        buf = self._album_buf.pop(key, None)
        self._album_tasks.pop(key, None)

        if not buf:
            return

        async with session() as s:
            # Создаём пост
            post = Post(
                source_chat_id=buf["chat_id"],
                source_message_id=buf["first_msg_id"],
                media_group_id=buf["group_id"],
                original_text=buf["text"] or "",
                notified=0,
            )
            s.add(post)
            await s.flush()

            # Добавляем медиа (храним message_id, не file_id)
            for idx, mid in enumerate(sorted(buf["media_msg_ids"])):
                s.add(MediaItem(
                    post_id=post.id,
                    kind="media",
                    file_id=str(mid),  # Храним message_id
                    sort_index=idx
                ))

            await s.commit()

            # Уведомляем админов
            await self._notify_admins(post.id, buf["text"], len(buf["media_msg_ids"]))

    async def _save_single_post(self, chat_id: int, msg_id: int, text: str, message: Message):
        """Сохранить одиночный пост"""
        has_file = self.has_real_file(message)

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
                    file_id=str(msg_id),  # Храним message_id
                    sort_index=0
                ))

            await s.commit()

            await self._notify_admins(post.id, text, 1 if has_file else 0)

    async def _notify_admins(self, post_id: int, text: str, media_count: int):
        """Уведомить админов о новом посте"""
        if not self._bot:
            logger.warning("Bot not set, cannot notify admins")
            return

        from src.keyboards.inline import post_actions_kb

        preview = (text or "")[:500]
        if len(text or "") > 500:
            preview += "…"

        media_info = f"\n\nВложения: {media_count}" if media_count else ""
        msg = f"🆕 Новый пост{media_info}\n\n{preview if preview else '(без текста)'}"

        for admin_id in settings.ADMIN_IDS:
            try:
                await self._bot.send_message(admin_id, msg, reply_markup=post_actions_kb(post_id))
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")

    async def get_channel_info(self, identifier: str) -> dict | None:
        """Получить информацию о канале"""
        if not self.client:
            return None

        try:
            if identifier.startswith("@"):
                identifier = identifier[1:]
            elif "t.me/" in identifier:
                identifier = identifier.split("t.me/")[1].split("/")[0].split("?")[0]

            entity = await self.client.get_entity(identifier)

            if isinstance(entity, TelethonChannel):
                return {
                    "chat_id": -int(f"100{entity.id}"),
                    "title": entity.title,
                }
        except Exception as e:
            logger.error(f"Failed to get channel info: {e}")

        return None

    def invalidate_cache(self):
        """Сбросить кеш"""
        self._cache_updated = 0

    @property
    def is_connected(self) -> bool:
        return self.client is not None and self.client.is_connected()


userbot = UserBot()