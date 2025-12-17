from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def sources_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список источников", callback_data="src:list")],
        [InlineKeyboardButton(text="➕ Добавить источник", callback_data="src:add")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="src:back_admin")],
    ])


def sources_list_kb(sources: list, page: int = 0) -> InlineKeyboardMarkup:
    buttons = []
    per_page = 8
    start = page * per_page
    end = start + per_page

    for src in sources[start:end]:
        status = "✅" if src.is_active else "❌"
        name = src.title or str(src.chat_id)
        if len(name) > 25:
            name = name[:22] + "..."
        buttons.append([
            InlineKeyboardButton(text=f"{status} {name}", callback_data=f"src:view:{src.id}")
        ])

    # Пагинация
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"src:page:{page - 1}"))
    if end < len(sources):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"src:page:{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="src:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def source_detail_kb(source_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle = "❌ Отключить" if is_active else "✅ Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle, callback_data=f"src:toggle:{source_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"src:del:{source_id}")],
        [InlineKeyboardButton(text="◀️ К списку", callback_data="src:list")],
    ])


def confirm_delete_kb(source_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"src:del_yes:{source_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"src:view:{source_id}"),
        ]
    ])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="src:menu")]
    ])
