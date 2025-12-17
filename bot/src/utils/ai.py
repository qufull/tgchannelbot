import anthropic

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from src.utils.config import settings
from src.utils.db import session
from src.models.ai_settings import AISettings

# Дефолтные значения
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

DEFAULT_PROMPTS = {
    "std": """
Напиши цепляющий, но не кликбейтный заголовок жирным шрифтом <b>. Заголовок должен быть релеватным и точным.

Не искажай и не меняй имена собственные и названия.

Перепиши текст в обывательском стиле, но от себя ничего не добавляй. Пиши от моего лица. Не используй знак *, НЕ ПРИЗЫВАЙ ПОДПИСАТЬ ИЛИ ЗАГЛЯНУТЬ НА МОЙ КАНАЛ В КОНЦЕ ТЕКСТА. 

Разделяй текст на абзацы. Избегай воды в тексте. От себя ничего не придумывай

Не используй эмодзи. Не используй знаки "*"

В тексте {ссылка на текст} оставь только ссылку на источник: {{ссылка на источник}}

в формате: <a href=\"URL\">Text</a> 

2) В конце текста вставь ссылку на канал без лишнего: 

3)  <a href="https://t.me/skynetaivpn_bot">ТРИ | БУКВЫ</a>

4) Так же вставь ссылку без лишнего: <a href="https://t.me/Sky_Net_AI">SkyNet Ai | ПОДПИСАТЬСЯ</a>

НЕ ПРИЗЫВАЙ ПОДПИСАТЬ ИЛИ ЗАГЛЯНУТЬ НА МОЙ КАНАЛ В КОНЦЕ ТЕКСТА.""",

    "short": """Ты — копирайтер. Сократи текст поста максимально:
- Оставь только самую важную информацию
- Убери всё лишнее, воду, повторы
- Сделай текст лаконичным (2-3 предложения если возможно)
- Сохрани язык оригинала""",

    "creative": """Ты — креативный SMM-специалист. Перепиши пост креативно:
- Добавь цепляющий заголовок
- Используй эмодзи уместно
- Сделай текст эмоциональным и вовлекающим
- Можешь добавить призыв к действию
- Сохрани ключевой смысл
- Пиши на том же языке, что и оригинал"""
}


def is_enabled() -> bool:
    """Проверяет, задан ли API-ключ Anthropic"""
    return bool(settings.ANTHROPIC_API_KEY)


async def get_ai_setting(key: str, default: str = "") -> str:
    """Получить настройку AI из БД"""
    async with session() as s:
        result = await s.execute(
            select(AISettings.value).where(AISettings.key == key)
        )
        row = result.scalar()
        return row if row is not None else default


async def set_ai_setting(key: str, value: str) -> None:
    """Установить настройку AI в БД (upsert)"""
    async with session() as s:
        stmt = (
            insert(AISettings)
            .values(key=key, value=value)
            .on_conflict_do_update(
                index_elements=[AISettings.key],
                set_={"value": value}
            )
        )
        await s.execute(stmt)
        await s.commit()


async def get_model() -> str:
    """Получить текущую модель Claude"""
    return await get_ai_setting("model", DEFAULT_MODEL)


async def set_model(model: str) -> None:
    """Установить модель Claude"""
    await set_ai_setting("model", model)


async def get_prompt(mode: str = "std") -> str:
    """Получить промпт для режима переписывания"""
    key = f"prompt_{mode}" if mode != "std" else "prompt"
    default = DEFAULT_PROMPTS.get(mode, DEFAULT_PROMPTS["std"])
    return await get_ai_setting(key, default)


async def set_prompt(mode: str, prompt: str) -> None:
    """Установить промпт для режима переписывания"""
    key = f"prompt_{mode}" if mode != "std" else "prompt"
    await set_ai_setting(key, prompt)


async def get_all_settings() -> dict:
    """Получить все настройки AI"""
    model = await get_model()
    prompts = {}
    for mode in ["std", "short", "creative"]:
        prompts[mode] = await get_prompt(mode)
    return {"model": model, "prompts": prompts}


async def rewrite_text(text: str, mode: str = "std") -> str:
    """
    Переписать текст с помощью Claude API

    mode:
      - "std" — стандартный рерайт
      - "short" — сокращённый
      - "creative" — креативный
    """
    if not is_enabled():
        raise RuntimeError("ANTHROPIC_API_KEY не задан")

    if not text.strip():
        return ""

    model = await get_model()
    system_prompt = await get_prompt(mode)

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        messages=[
            {"role": "user", "content": text}
        ]
    )

    return message.content[0].text.strip()


# Список доступных моделей Claude для выбора
AVAILABLE_MODELS = [
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5-20250929",
    "claude-opus-4-5-20251101",
]