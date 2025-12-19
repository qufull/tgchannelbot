"""
src/userbot/publisher.py
Публикация постов через юзербот (с поддержкой альбомов)
"""

import re
import logging
from telethon.tl.types import MessageMediaWebPage

from src.utils.tg_format import md_to_html, split_html_safe

logger = logging.getLogger(__name__)


def has_sendable_media(msg) -> bool:
    if not msg or not msg.media:
        return False
    if isinstance(msg.media, MessageMediaWebPage):
        return False
    return bool(msg.photo or msg.video or msg.document or msg.audio or msg.voice)



async def publish_post(client, target_chat_id: int, text: str, source_chat_id: int, source_message_id: int, has_media: bool) -> bool:
    if not client or not client.is_connected():
        logger.error("Client not connected")
        return False

    html_text = md_to_html(text)

    try:
        if has_media and source_chat_id and source_message_id:
            msg = await client.get_messages(source_chat_id, ids=source_message_id)

            if msg and msg.grouped_id:
                return await publish_album(client, target_chat_id, html_text, source_chat_id, msg)

            elif msg and has_sendable_media(msg):
                await client.send_file(
                    target_chat_id,
                    msg.media,
                    caption=html_text,
                    parse_mode="html"
                )
                return True

        await send_long_text(client, target_chat_id, html_text, parse_mode="html")
        return True

    except Exception as e:
        logger.error(f"Publish failed: {e}")
        return False

async def publish_album(client, target_chat_id: int, caption_html: str, source_chat_id: int, first_msg) -> bool:
    try:
        grouped_id = first_msg.grouped_id
        messages = await client.get_messages(
            source_chat_id,
            limit=30,
            max_id=first_msg.id + 20,
            min_id=first_msg.id - 20
        )
        album_msgs = [m for m in messages if m.grouped_id == grouped_id and has_sendable_media(m)]
        album_msgs.sort(key=lambda m: m.id)

        if not album_msgs:
            return False

        media_list = [m.media for m in album_msgs]

        await client.send_file(
            target_chat_id,
            media_list,
            caption=caption_html,
            parse_mode="html"
        )
        return True
    except Exception as e:
        logger.error(f"Album publish failed: {e}")
        return False

async def send_long_text(client, chat_id: int, html_text: str, parse_mode: str = "html"):
    if not html_text:
        return

    for chunk in split_html_safe(html_text, limit=4096):
        await client.send_message(chat_id, chunk, parse_mode=parse_mode, link_preview=False)
