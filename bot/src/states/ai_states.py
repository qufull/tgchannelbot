from aiogram.fsm.state import State, StatesGroup


class AISettingsStates(StatesGroup):
    wait_prompt = State()
    wait_custom_model = State()
