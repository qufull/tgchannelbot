from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def admin_menu_kb() -> InlineKeyboardMarkup:
    """Главное меню админки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📡 Источники", callback_data="adm:sources")],
        [InlineKeyboardButton(text="🎯 Целевой канал", callback_data="adm:set_target")],
        [InlineKeyboardButton(text="🔌 Подключения", callback_data="adm:list_links")],
        [InlineKeyboardButton(text="⚙️ Настройки AI", callback_data="adm:ai_settings")],
    ])


def rewrite_modes_kb(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Стандартный", callback_data=f"p:{post_id}:rw:std")],
        [InlineKeyboardButton(text="✂️ Короткий", callback_data=f"p:{post_id}:rw:short")],
        [InlineKeyboardButton(text="🎨 Креативный", callback_data=f"p:{post_id}:rw:creative")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"p:{post_id}:back")],
    ])


def post_actions_kb(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✍️ Переписать", callback_data=f"p:{post_id}:rewrite"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"p:{post_id}:delete"),
        ],
        [InlineKeyboardButton(text="📤 Опубликовать", callback_data=f"p:{post_id}:publish")],
    ])