"""
src/userbot/client.py
Telethon клиент — подключение и базовые методы
"""

import logging
import re

from aiogram import Bot
from telethon import TelegramClient, events
from telethon.tl.types import Channel as TelethonChannel
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import (
    UserAlreadyParticipantError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    ChannelPrivateError
)

from src.utils.config import settings
from src.userbot.monitor import monitor

logger = logging.getLogger(__name__)


class UserBot:
    """Telethon клиент для юзербота"""

    def __init__(self):
        self.client: TelegramClient | None = None

    def set_bot(self, bot: Bot):
        """Передать aiogram бота для уведомлений"""
        monitor.set_bot(bot)

    async def start(self):
        """Запуск юзербота"""
        self.client = TelegramClient(
            'userbot_session',
            settings.API_ID,
            settings.API_HASH
        )

        await self.client.start(phone=settings.PHONE)

        logger.info("Userbot connected")

        monitor.set_client(self.client)
        self.client.add_event_handler(
            self._on_new_message,
            events.NewMessage()
        )

        logger.info("Userbot handlers registered")

    async def stop(self):
        """Остановка"""
        if self.client:
            await self.client.disconnect()
            logger.info("Userbot disconnected")

    async def run_until_disconnected(self):
        """Держим соединение"""
        if self.client:
            await self.client.run_until_disconnected()

    async def _on_new_message(self, event: events.NewMessage.Event):
        """Обработчик новых сообщений"""
        try:
            chat = await event.get_chat()
            if isinstance(chat, TelethonChannel):
                await monitor.on_message(chat, event.message)
        except Exception as e:
            logger.exception(f"Error handling message: {e}")

    async def get_channel_info(self, identifier: str) -> dict | None:
        """Получить информацию о канале (публичном или уже подписанном)"""
        if not self.client:
            return None

        try:
            clean = self._clean_identifier(identifier)
            logger.info(f"Getting channel info: {clean}")

            entity = await self.client.get_entity(clean)

            if isinstance(entity, TelethonChannel):
                return {
                    "chat_id": -int(f"100{entity.id}"),
                    "title": entity.title,
                }
        except ChannelPrivateError:
            logger.warning(f"Channel is private, need to join first")
        except Exception as e:
            logger.error(f"Failed to get channel info: {e}")

        return None

    async def join_channel(self, invite_link: str) -> dict | None:
        """
        Вступить в канал по ссылке.
        """
        if not self.client:
            logger.error("Client not initialized")
            return None

        logger.info(f"join_channel called with: {invite_link}")

        try:
            # Извлекаем hash для приватных ссылок
            invite_hash = self._extract_invite_hash(invite_link)

            if invite_hash:
                # Приватная ссылка
                logger.info(f"Private link detected, hash: {invite_hash}")
                return await self._join_private(invite_hash)
            else:
                # Публичный канал
                username = self._clean_identifier(invite_link)
                logger.info(f"Public channel detected: {username}")
                return await self._join_public(username)

        except Exception as e:
            logger.exception(f"join_channel failed: {e}")
            return None

    def _extract_invite_hash(self, link: str) -> str | None:
        """Извлечь hash из invite-ссылки"""
        # t.me/+ABC123 или https://t.me/+ABC123
        match = re.search(r't\.me/\+([a-zA-Z0-9_-]+)', link)
        if match:
            return match.group(1)

        # t.me/joinchat/ABC123
        match = re.search(r't\.me/joinchat/([a-zA-Z0-9_-]+)', link)
        if match:
            return match.group(1)

        return None

    def _clean_identifier(self, link: str) -> str:
        """Очистить идентификатор канала"""
        # @channel
        if link.startswith("@"):
            return link[1:]

        # t.me/channel
        match = re.search(r't\.me/([a-zA-Z][a-zA-Z0-9_]+)', link)
        if match:
            username = match.group(1)
            if username not in ("joinchat",):
                return username

        return link

    async def _join_private(self, invite_hash: str) -> dict | None:
        """Вступить в приватный канал"""
        try:
            logger.info(f"Calling ImportChatInviteRequest({invite_hash})")
            result = await self.client(ImportChatInviteRequest(invite_hash))

            chat = result.chats[0]
            logger.info(f"Joined private channel: {chat.title}")

            return {
                "chat_id": -int(f"100{chat.id}"),
                "title": chat.title,
            }

        except UserAlreadyParticipantError:
            logger.info("Already a participant, trying to get entity...")
            try:
                # Пробуем получить через hash
                entity = await self.client.get_entity(f"https://t.me/+{invite_hash}")
                if isinstance(entity, TelethonChannel):
                    return {
                        "chat_id": -int(f"100{entity.id}"),
                        "title": entity.title,
                    }
            except Exception as e:
                logger.error(f"Failed to get entity after already participant: {e}")
            return None

        except InviteHashExpiredError:
            logger.error("Invite link has expired")
            return None

        except InviteHashInvalidError:
            logger.error("Invalid invite hash")
            return None

        except Exception as e:
            logger.exception(f"_join_private failed: {e}")
            return None

    async def _join_public(self, username: str) -> dict | None:
        """Вступить в публичный канал"""
        try:
            logger.info(f"Calling JoinChannelRequest({username})")
            result = await self.client(JoinChannelRequest(username))

            chat = result.chats[0]
            logger.info(f"Joined public channel: {chat.title}")

            return {
                "chat_id": -int(f"100{chat.id}"),
                "title": chat.title,
            }

        except UserAlreadyParticipantError:
            logger.info("Already a participant")
            return await self.get_channel_info(username)

        except Exception as e:
            logger.exception(f"_join_public failed: {e}")
            return None

    def invalidate_cache(self):
        """Сбросить кеш источников"""
        monitor.invalidate_cache()

    @property
    def is_connected(self) -> bool:
        return self.client is not None and self.client.is_connected()


# Глобальный экземпляр
userbot = UserBot()