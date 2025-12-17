from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Message


def split_text(text: str, limit: int) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []

    parts: list[str] = []
    buf = ""

    # режем по абзацам, потом по словам
    paragraphs = text.split("\n")
    for p in paragraphs:
        chunk = (p + "\n").strip("\n")
        if not chunk:
            candidate = "\n"
        else:
            candidate = chunk + "\n"

        if len(buf) + len(candidate) <= limit:
            buf += candidate
            continue

        if buf.strip():
            parts.append(buf.strip())
            buf = ""

        # если абзац сам длиннее лимита — режем по словам
        if len(candidate) > limit:
            words = candidate.split(" ")
            line = ""
            for w in words:
                add = (w + " ") if w else ""
                if len(line) + len(add) <= limit:
                    line += add
                else:
                    if line.strip():
                        parts.append(line.strip())
                    line = add
            if line.strip():
                parts.append(line.strip())
        else:
            buf = candidate

    if buf.strip():
        parts.append(buf.strip())

    return parts

TELEGRAM_TEXT_LIMIT = 4096
TELEGRAM_CAPTION_LIMIT = 1024

def make_caption_and_rest(full_text: str) -> tuple[str, str]:
    full_text = (full_text or "").strip()
    if not full_text:
        return "", ""

    if len(full_text) <= TELEGRAM_CAPTION_LIMIT:
        return full_text, ""

    caption = full_text[:TELEGRAM_CAPTION_LIMIT].rstrip()
    # чтобы не резать посреди слова — чуть откатим
    if " " in caption:
        caption = caption.rsplit(" ", 1)[0].rstrip()

    rest = full_text[len(caption):].lstrip()
    return caption, rest


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


async def hide_message(msg: Message, fallback_text: str = "✅ Готово"):
    try:
        await msg.delete()
        return
    except (TelegramBadRequest, TelegramForbiddenError):
        pass

    try:
        await msg.edit_text(fallback_text, reply_markup=None)
    except TelegramBadRequest:
        pass
