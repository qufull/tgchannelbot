"""
src/keyboards/ai_keyboard.py
Клавиатуры для настроек AI
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.utils.ai import AVAILABLE_MODELS


def ai_settings_kb() -> InlineKeyboardMarkup:
    """Меню настроек AI"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Изменить модель", callback_data="ai:select_model")],
        [InlineKeyboardButton(text="📝 Промпт (стандартный)", callback_data="ai:edit_prompt:std")],
        [InlineKeyboardButton(text="✂️ Промпт (короткий)", callback_data="ai:edit_prompt:short")],
        [InlineKeyboardButton(text="🎨 Промпт (креативный)", callback_data="ai:edit_prompt:creative")],
        [InlineKeyboardButton(text="📊 Показать все настройки", callback_data="ai:show_settings")],
        [InlineKeyboardButton(text="🔄 Сбросить на дефолт", callback_data="ai:reset")],
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="ai:back_to_admin")],
    ])


def models_kb(current_model: str = "") -> InlineKeyboardMarkup:
    """Клавиатура выбора модели Claude"""
    buttons = []

    model_names = {
        "claude-3-5-sonnet-20241022": "Claude 3.5 Sonnet",
        "claude-3-5-haiku-20241022": "Claude 3.5 Haiku (быстрый)",
        "claude-3-opus-20240229": "Claude 3 Opus (мощный)",
        "claude-3-sonnet-20240229": "Claude 3 Sonnet",
        "claude-3-haiku-20240307": "Claude 3 Haiku",
    }

    for model in AVAILABLE_MODELS:
        name = model_names.get(model, model)
        if model == current_model:
            name = f"✅ {name}"
        buttons.append([
            InlineKeyboardButton(text=name, callback_data=f"ai:set_model:{model}")
        ])

    # Кнопка для ввода своей модели
    buttons.append([
        InlineKeyboardButton(text="✏️ Ввести свою модель", callback_data="ai:custom_model")
    ])

    buttons.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="ai:back")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_reset_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, сбросить", callback_data="ai:confirm_reset"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="ai:back"),
        ]
    ])


def back_to_ai_settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ К настройкам AI", callback_data="ai:back")]
    ])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="ai:back")]
    ])