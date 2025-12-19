from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Message


def extract_forwarded_channel_id(m: Message) -> tuple[int | None, str]:

    fo = getattr(m, "forward_origin", None)
    if fo and getattr(fo, "chat", None):
        ch = fo.chat
        return ch.id, (ch.title or "")

    return None, ""

async def safe_delete_message(bot: Bot, chat_id: int, message_id: int) -> bool:
    """
    Безопасно удалить сообщение.
    Возвращает True если удалено, False если не удалось.
    """
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except (TelegramBadRequest, TelegramForbiddenError):
        # Сообщение уже удалено или нет прав
        return False
    except Exception:
        return False
