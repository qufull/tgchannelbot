"""
src/userbot/publisher.py
Публикация постов через юзербот (с поддержкой альбомов)
"""

import re
import logging
from telethon.tl.types import MessageMediaWebPage

logger = logging.getLogger(__name__)


def markdown_to_html(text: str) -> str:
    """
    Конвертирует markdown в HTML для Telegram.
    """
    if not text:
        return text

    # Пропускаем если уже есть HTML теги
    if not re.search(r'<(b|i|u|s|a|code|pre|strong|em)[\s>]', text, re.IGNORECASE):
        # **жирный**
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)

        # *курсив*
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
        text = re.sub(r'(?<!_)_(?!_)(.+?)(?<!_)_(?!_)', r'<i>\1</i>', text)

        # ~~зачёркнутый~~
        text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)

        # `код`
        text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)

        # [текст](url)
        text = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', text)

    return text


def has_sendable_media(msg) -> bool:
    """Проверяет, есть ли медиа для отправки как файл"""
    if not msg or not msg.media:
        return False
    if isinstance(msg.media, MessageMediaWebPage):
        return False
    return bool(msg.photo or msg.video or msg.document or msg.audio or msg.voice)


async def publish_post(client, target_chat_id: int, text: str, source_chat_id: int, source_message_id: int, has_media: bool) -> bool:
    """
    Публикует пост через юзербот.

    Args:
        client: Telethon клиент
        target_chat_id: ID целевого канала
        text: Текст поста
        source_chat_id: ID источника
        source_message_id: ID первого сообщения
        has_media: Есть ли медиа
    """
    if not client or not client.is_connected():
        logger.error("Client not connected")
        return False

    html_text = markdown_to_html(text)

    try:
        if has_media and source_chat_id and source_message_id:
            # Получаем сообщение
            msg = await client.get_messages(source_chat_id, ids=source_message_id)

            if msg and msg.grouped_id:
                # Это альбом — получаем все сообщения группы
                return await publish_album(client, target_chat_id, html_text, source_chat_id, msg)

            elif msg and has_sendable_media(msg):
                # Одиночное медиа
                await client.send_file(
                    target_chat_id,
                    msg.media,
                    caption=html_text,
                    parse_mode="html"
                )
                logger.info(f"Published single media to {target_chat_id}")
                return True

        # Только текст
        await send_long_text(client, target_chat_id, html_text)
        logger.info(f"Published text to {target_chat_id}")
        return True

    except Exception as e:
        logger.error(f"Publish failed: {e}")
        return False


async def publish_album(client, target_chat_id: int, text: str, source_chat_id: int, first_msg) -> bool:
    """
    Публикует альбом (группу медиа).
    """
    try:
        grouped_id = first_msg.grouped_id

        # Получаем сообщения вокруг первого (альбом идёт подряд)
        messages = await client.get_messages(
            source_chat_id,
            limit=15,
            max_id=first_msg.id + 10,
            min_id=first_msg.id - 5
        )

        # Фильтруем только сообщения этого альбома
        album_msgs = [m for m in messages if m.grouped_id == grouped_id and has_sendable_media(m)]
        album_msgs.sort(key=lambda m: m.id)

        if not album_msgs:
            logger.warning("No album messages found")
            return False

        # Собираем медиа
        media_list = [m.media for m in album_msgs]

        # Отправляем альбом
        await client.send_file(
            target_chat_id,
            media_list,
            caption=text,
            parse_mode="html"
        )

        logger.info(f"Published album ({len(media_list)} items) to {target_chat_id}")
        return True

    except Exception as e:
        logger.error(f"Album publish failed: {e}")
        return False


async def send_long_text(client, chat_id: int, text: str, parse_mode: str = "html"):
    """Отправляет длинный текст частями"""
    if not text:
        return

    if len(text) <= 4096:
        await client.send_message(chat_id, text, parse_mode=parse_mode, link_preview=False)
    else:
        for i in range(0, len(text), 4096):
            await client.send_message(chat_id, text[i:i+4096], parse_mode=parse_mode,link_preview=False)