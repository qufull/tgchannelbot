from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def start_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⚙️ Админка")]],
        resize_keyboard=True,
        one_time_keyboard=False
    )