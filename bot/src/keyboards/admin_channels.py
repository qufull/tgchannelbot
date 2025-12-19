from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def sources_menu_kb() -> InlineKeyboardMarkup:
    """Меню источников"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список", callback_data="src:list")],
        [InlineKeyboardButton(text="➕ Добавить", callback_data="src:add")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="src:main")],
    ])


def sources_list_kb(sources: list) -> InlineKeyboardMarkup:
    """Список источников"""
    buttons = []
    for src in sources:
        status = "✅" if src.is_active else "⏸"
        buttons.append([
            InlineKeyboardButton(
                text=f"{status} {src.title}",
                callback_data=f"src:view:{src.id}"
            )
        ])

    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="src:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def source_actions_kb(channel_id: int, is_active: bool) -> InlineKeyboardMarkup:
    """Действия с источником"""
    toggle_text = "⏸ Приостановить" if is_active else "▶️ Включить"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data=f"src:toggle:{channel_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"src:delete:{channel_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="src:list")],
    ])
