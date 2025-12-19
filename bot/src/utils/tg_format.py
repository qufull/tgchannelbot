import re
from html import escape as html_escape
from typing import List, Tuple

_HTML_TAG_RE = re.compile(r"</?(b|i|u|s|a|code|pre|strong|em)\b", re.IGNORECASE)

def md_to_html(text: str) -> str:
    """
    Markdown -> HTML для Telegram:
    - **bold**, _italic_, ~~strike~~, `code`
    - [text](url) и [text] url -> <a href="url">text</a>
    ВАЖНО: если текст уже похож на HTML — возвращаем как есть (чтобы не портить).
    """
    if not text:
        return ""

    raw = text.strip()

    # если AI уже вернул HTML — НЕ трогаем
    if _HTML_TAG_RE.search(raw):
        return raw

    links: List[Tuple[str, str]] = []

    def repl_link(m: re.Match) -> str:
        label = m.group(1)
        url = m.group(2)
        token = f"§§LINK{len(links)}§§"
        links.append((label, url))
        return token

    # [label](url)
    raw = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", repl_link, raw)
    # [label] url
    raw = re.sub(r"\[([^\]]+)\]\s*(https?://\S+)", repl_link, raw)

    # экранируем всё
    t = html_escape(raw)

    # базовая разметка
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"__(.+?)__", r"<b>\1</b>", t)
    t = re.sub(r"~~(.+?)~~", r"<s>\1</s>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    t = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<i>\1</i>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", t)

    # вернуть ссылки
    for i, (label, url) in enumerate(links):
        url_html = html_escape(url, quote=True)
        label_html = html_escape(label)
        label_html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", label_html)
        label_html = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<i>\1</i>", label_html)
        t = t.replace(f"§§LINK{i}§§", f'<a href="{url_html}">{label_html}</a>')

    return t.strip()


def _safe_cut_html(html_text: str, limit: int) -> int:
    """
    Возвращает позицию разреза <= limit так, чтобы:
    - не резать внутри <...>
    - не резать внутри <a ...>...</a>
    """
    if len(html_text) <= limit:
        return len(html_text)

    # стараемся резать по переносу
    cut = html_text.rfind("\n", 0, limit)
    if cut < max(50, int(limit * 0.3)):
        cut = limit

    # не резать внутри тега по счетчику < >
    while cut > 0:
        seg = html_text[:cut]
        if seg.count("<") <= seg.count(">"):
            break
        cut = html_text.rfind("\n", 0, cut - 1)
        if cut == -1:
            cut = limit
            break

    # не резать внутри <a ...>...</a>
    seg = html_text[:cut]
    if seg.lower().count("<a ") > seg.lower().count("</a>"):
        last_a = seg.lower().rfind("<a ")
        if last_a > 0:
            cut = last_a

    return cut


def split_html_safe(html_text: str, limit: int = 4096) -> List[str]:
    """
    Режет HTML на сообщения, НЕ ломая теги.
    """
    parts: List[str] = []
    t = html_text.strip()
    while t:
        if len(t) <= limit:
            parts.append(t)
            break

        cut = _safe_cut_html(t, limit)
        head = t[:cut].strip()
        parts.append(head)
        t = t[cut:].lstrip()

    return parts


def split_caption_and_tail(html_text: str, caption_limit: int = 1024) -> tuple[str, str]:
    """
    Делит HTML на caption (<=1024) и остаток.
    """
    if len(html_text) <= caption_limit:
        return html_text, ""

    cut = _safe_cut_html(html_text, caption_limit)
    caption = html_text[:cut].strip()
    tail = html_text[cut:].lstrip()
    return caption, tail