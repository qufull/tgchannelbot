

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.state import State, StatesGroup

from src.keyboards.ai_keyboard import (
    ai_settings_kb,
    models_kb,
    confirm_reset_kb,
    back_to_ai_settings_kb,
    cancel_kb,
)
from src.keyboards.inline import admin_menu_kb
from src.utils.ai import (
    get_model,
    set_model,
    get_prompt,
    set_prompt,
    get_all_settings,
    DEFAULT_MODEL,
    DEFAULT_PROMPTS,
    AVAILABLE_MODELS,
)

router = Router()


# ─────────────────────────────────────────────────────────────
# FSM состояния
# ─────────────────────────────────────────────────────────────

class AISettingsStates(StatesGroup):
    wait_prompt = State()
    wait_custom_model = State()  # Ожидание ввода своей модели


# ─────────────────────────────────────────────────────────────
# Выбор модели
# ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "ai:select_model")
async def select_model_menu(c: CallbackQuery):
    """Показать список моделей для выбора"""
    current = await get_model()
    await c.message.edit_text(
        f"🤖 <b>Выбор модели Claude</b>\n\n"
        f"Текущая: <code>{current}</code>\n\n"
        f"Выберите из списка или введите свою:",
        reply_markup=models_kb(current),
        parse_mode="HTML"
    )
    await c.answer()


@router.callback_query(F.data.startswith("ai:set_model:"))
async def set_model_handler(c: CallbackQuery):
    """Установить выбранную модель из списка"""
    model = c.data.split(":", 2)[2]

    await set_model(model)
    await c.answer(f"✅ Модель установлена!", show_alert=True)

    await c.message.edit_text(
        f"⚙️ <b>Настройки AI</b>\n\n"
        f"Текущая модель: <code>{model}</code>\n\n"
        f"Выберите действие:",
        reply_markup=ai_settings_kb(),
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────────────────────
# Ввод своей модели
# ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "ai:custom_model")
async def custom_model_start(c: CallbackQuery, state: FSMContext):
    """Начать ввод своей модели"""
    await state.set_state(AISettingsStates.wait_custom_model)

    await c.message.edit_text(
        "✏️ <b>Ввод своей модели</b>\n\n"
        "Отправьте название модели Claude.\n\n"
        "Примеры:\n"
        "• <code>claude-sonnet-4-5-20250929</code>\n"
        "• <code>claude-haiku-4-5-20251001</code>\n"
        "• <code>claude-opus-4-5-20251101</code>\n\n"
        "Актуальные модели: https://docs.anthropic.com/en/docs/about-claude/models",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await c.answer()


@router.message(AISettingsStates.wait_custom_model)
async def save_custom_model(m: Message, state: FSMContext):
    """Сохранить введённую модель"""
    model_name = (m.text or "").strip()

    # Базовая валидация
    if not model_name:
        await m.answer("⚠️ Введите название модели:")
        return

    if len(model_name) < 5:
        await m.answer("⚠️ Слишком короткое название. Введите корректное название модели:")
        return

    if len(model_name) > 100:
        await m.answer("⚠️ Слишком длинное название. Введите корректное название модели:")
        return

    # Предупреждение если модель не из известного списка
    warning = ""
    if model_name not in AVAILABLE_MODELS and not model_name.startswith("claude-"):
        warning = "\n\n⚠️ Модель не похожа на Claude. Убедитесь, что название верное."

    await set_model(model_name)
    await state.clear()

    await m.answer(
        f"✅ Модель установлена: <code>{model_name}</code>{warning}",
        reply_markup=ai_settings_kb(),
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────────────────────
# Редактирование промптов
# ─────────────────────────────────────────────────────────────

MODE_NAMES = {
    "std": "Стандартный",
    "short": "Короткий",
    "creative": "Креативный",
}


@router.callback_query(F.data.startswith("ai:edit_prompt:"))
async def edit_prompt_start(c: CallbackQuery, state: FSMContext):
    """Начать редактирование промпта"""
    mode = c.data.split(":")[2]

    if mode not in MODE_NAMES:
        await c.answer("Неизвестный режим", show_alert=True)
        return

    current_prompt = await get_prompt(mode)
    await state.set_state(AISettingsStates.wait_prompt)
    await state.update_data(mode=mode)

    preview = current_prompt[:1500] if len(current_prompt) > 1500 else current_prompt

    await c.message.edit_text(
        f"📝 <b>Редактирование промпта: {MODE_NAMES[mode]}</b>\n\n"
        f"Текущий промпт:\n"
        f"<pre>{_escape_html(preview)}</pre>\n\n"
        f"Отправьте новый текст промпта:",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await c.answer()


@router.message(AISettingsStates.wait_prompt)
async def save_new_prompt(m: Message, state: FSMContext):
    """Сохранить новый промпт"""
    data = await state.get_data()
    mode = data.get("mode", "std")

    new_prompt = (m.text or "").strip()
    if len(new_prompt) < 10:
        await m.answer("⚠️ Промпт слишком короткий (минимум 10 символов). Попробуйте ещё раз:")
        return

    await set_prompt(mode, new_prompt)
    await state.clear()

    preview = new_prompt[:500] if len(new_prompt) > 500 else new_prompt

    await m.answer(
        f"✅ Промпт <b>{MODE_NAMES.get(mode, mode)}</b> сохранён!\n\n"
        f"<pre>{_escape_html(preview)}</pre>",
        reply_markup=ai_settings_kb(),
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────────────────────
# Показать текущие настройки
# ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "ai:show_settings")
async def show_all_settings(c: CallbackQuery):
    """Показать все текущие настройки AI"""
    settings_data = await get_all_settings()

    text = f"📊 <b>Текущие настройки AI</b>\n\n"
    text += f"🤖 <b>Модель:</b>\n<code>{settings_data['model']}</code>\n\n"

    for mode, prompt in settings_data["prompts"].items():
        name = MODE_NAMES.get(mode, mode)
        preview = prompt
        text += f"📝 <b>{name}:</b>\n<pre>{_escape_html(preview)}</pre>\n\n"

    await c.message.edit_text(
        text,
        reply_markup=back_to_ai_settings_kb(),
        parse_mode="HTML"
    )
    await c.answer()


# ─────────────────────────────────────────────────────────────
# Сброс настроек
# ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "ai:reset")
async def confirm_reset(c: CallbackQuery):
    """Запросить подтверждение сброса"""
    await c.message.edit_text(
        "⚠️ <b>Сброс настроек AI</b>\n\n"
        "Вы уверены, что хотите сбросить все настройки?\n\n"
        f"Модель станет: <code>{DEFAULT_MODEL}</code>\n"
        "Все промпты вернутся к значениям по умолчанию.",
        reply_markup=confirm_reset_kb(),
        parse_mode="HTML"
    )
    await c.answer()


@router.callback_query(F.data == "ai:confirm_reset")
async def do_reset(c: CallbackQuery):
    """Выполнить сброс настроек"""
    await set_model(DEFAULT_MODEL)

    for mode, prompt in DEFAULT_PROMPTS.items():
        await set_prompt(mode, prompt)

    await c.answer("✅ Настройки сброшены!", show_alert=True)

    await c.message.edit_text(
        f"⚙️ <b>Настройки AI</b>\n\n"
        f"Текущая модель: <code>{DEFAULT_MODEL}</code>\n\n"
        f"Все настройки сброшены.",
        reply_markup=ai_settings_kb(),
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────────────────────
# Навигация
# ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "ai:back")
async def back_to_ai_settings(c: CallbackQuery, state: FSMContext):
    """Вернуться в меню настроек AI"""
    await state.clear()

    model = await get_model()
    await c.message.edit_text(
        f"⚙️ <b>Настройки AI</b>\n\n"
        f"Текущая модель: <code>{model}</code>\n\n"
        f"Выберите действие:",
        reply_markup=ai_settings_kb(),
        parse_mode="HTML"
    )
    await c.answer()


@router.callback_query(F.data == "ai:back_to_admin")
async def back_to_admin_menu(c: CallbackQuery, state: FSMContext):
    """Вернуться в главное меню админки"""
    await state.clear()
    await c.message.edit_text("Админка:", reply_markup=admin_menu_kb())
    await c.answer()


# ─────────────────────────────────────────────────────────────
# Утилиты
# ─────────────────────────────────────────────────────────────

def _escape_html(text: str) -> str:
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )